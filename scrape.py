#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import errno
import logging
import re
import sys

import click
import requests
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s: %(message)s")
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.ERROR)
handler.setFormatter(formatter)
logger.addHandler(handler)

metric_prefix = "cablemodem"


@click.command()
@click.option("--verbose", "-v", is_flag=True, default=False, help="log verbosely (to STDERR)")
@click.option("--debug", "-D", is_flag=True, default=False, help="log DEBUG messages overrides -v")
@click.option("--url", "-u", default="http://192.168.100.1", help="root URL for modem site")
@click.option("--prefix", "-p", default=metric_prefix, help="prefix for graphite metrics")
def main(verbose, url, prefix, debug):
    """
    Scrape Arris SB6183 metrics from the web page and print Graphite-formatted
    results to sdtout

    This is suited for an 'exec' type Telegraf plugin or can be piped to
    netcat to feed to Graphite itself.

    Logs/errors go to STDERR to not interfere with automation output.

    The HTML of the page is completely broken, so this is an ugly hack that
    may break for different versions.  Tested against
    D30CM-OSPREY-2.4.0.1-GA-02-NOSH

    This may also work for other models.
    """
    global metric_prefix

    if verbose:
        logger.setLevel(logging.INFO)
        handler.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
        handler.setLevel(logging.DEBUG)
    metric_prefix = prefix

    scrape_main(url)
    scrape_uptime(url)


def scrape_main(url):
    try:
        logger.debug(f"Requesting {url}")
        res = requests.get(url)
    except ConnectionError:
        logger.fatal(f"Could not connect to {url}, exiting")
        sys.exit(errno.EHOSTUNREACH)

    body = res.text
    body = clean_html(body)

    soup = BeautifulSoup(body, features="html.parser")

    metrics = parse_downstream(soup)
    metrics.update(parse_upstream(soup))

    graphite(metrics)


def scrape_uptime(url):
    full_url = f"{url}/RgSwInfo.asp"
    try:
        logger.debug(f"Requesting {full_url}")
        res = requests.get(full_url)
    except ConnectionError:
        logger.fatal(f"Could not connect to {full_url}, exiting")
        sys.exit(errno.EHOSTUNREACH)

    body = res.text
    body = clean_html(body)

    soup = BeautifulSoup(body, features="html.parser")

    uptime_str = find_uptime(soup)
    metrics = dict(uptime=parse_uptime(uptime_str))

    graphite(metrics)


def clean_html(body):

    logger.debug("Sanitizing HTML for parsing")
    # this can't even be souped...  so we clean up
    body = body.replace("=>", '="1" >')
    body = body.replace("\r", "")
    body = body.replace("\u0000", "\n")
    body = body.replace('<div class="spacer30"></div>', "<div>")
    body = body.replace(
        (
            '<form action=/goform/RgConnect method="post" name="RgConnect">'
            + '<table><tr><td><input type="hidden" name="GetNonce" size=31 '
            + 'value="1" > </td></tr></table>'
        ),
        "",
    )
    body = body.replace("</form>", "")
    body = body.replace('<div id="pw1">', "")
    body = body.replace('<div id="pw2">', "")
    body = body.replace('<div class="header">', "")
    return body


def parse_downstream(soup):
    logger.debug("Handling downstream metrics")

    downstream_columns = [
        "Channel",
        "Lock Status",
        "Modulation",
        "Channel ID",
        "Frequency",
        "Power",
        "SNR",
        "Corrected",
        "Uncorrectables",
    ]

    downstream_metrics = {}

    for row in soup.find_all("table")[1].find_all("tr"):
        # heading
        if row.find("th") is not None:
            continue
        # subheading
        if row.find("strong") is not None:
            continue
        channel = {}
        for idx, col in enumerate(row.find_all("td")):
            channel[downstream_columns[idx].lower()] = str(col.contents[0].split()[0])
            try:
                downstream_metrics[f"downstream_channel_{channel['channel']}"] = channel
            except KeyError:
                logger.error(f"Could not take apart {channel}")

    return downstream_metrics


def parse_upstream(soup):
    logger.debug("Handling upstream metrics")
    upstream_columns = [
        "Channel",
        "Lock Status",
        "US Channel Type",
        "Channel ID",
        "Symbol Rate",
        "Frequency",
        "Power",
    ]

    upstream_metrics = {}

    for row in soup.find_all("table")[2].find_all("tr"):
        # heading
        if row.find("th") is not None:
            continue
        # subheading
        if row.find("strong") is not None:
            continue
        channel = {}
        for idx, col in enumerate(row.find_all("td")):
            channel[upstream_columns[idx].lower()] = str(col.contents[0].split()[0])
            try:
                upstream_metrics[f"upstream_channel_{channel['channel']}"] = channel
            except KeyError:
                logger.error(f"wut? {channel['channel']}")

    return upstream_metrics


def find_uptime(soup):
    logger.debug("Handling uptime metric")
    uptime = soup.find_all("table")[1].find_all("tr")[1].find_all("td")[1].contents[0]
    return uptime


def print_graphite(key, value, ts):
    try:
        value = float(value)
    except ValueError:
        logger.debug(f"Expected NaN: {key}: {value}")
        return

    print(f"{metric_prefix}_{key} {value:f} {ts:f}")


def graphite(data):
    now = datetime.datetime.now().timestamp()

    for metric, value in data.items():
        if type(value) == dict:
            for key, sub in value.items():
                subkey_name = key.lower().replace(" ", "_")
                print_graphite(f"{metric}_{subkey_name}", sub, now)
        else:
            print_graphite(metric, value, now)


def parse_uptime(dstring):
    logger.debug(f"Turning bizarre string {dstring} into an interval")
    res = re.match(r"(?P<days>\d+) days (?P<hours>\d+)h:(?P<mins>\d+)m:(?P<secs>\d+)s", dstring)

    if res is None:
        logger.error(f"Invalid uptime string: {dstring}")
        return -1

    try:
        delta = datetime.timedelta(
            days=int(res.group("days")),
            hours=int(res.group("hours")),
            minutes=int(res.group("mins")),
            seconds=int(res.group("secs")),
        )
    except ValueError:
        logger.error(f"Invalid uptime string: {dstring}")
        return -1

    total_seconds = (delta.days * 86400) + delta.seconds
    return total_seconds


if __name__ == "__main__":
    main()
