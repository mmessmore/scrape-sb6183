#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys
from datetime import datetime

import click
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s: %(message)s")
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.ERROR)
handler.setFormatter(formatter)
logger.addHandler(handler)


@click.command()
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.option("--url", "-u", default="http://192.168.0.1")
def main(verbose, url):
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

    if verbose:
        logger.setLevel(logging.INFO)
        handler.setLevel(logging.INFO)

    res = requests.get(url)
    body = res.text

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

    soup = BeautifulSoup(body, features="html.parser")

    metrics = parse_downstream(soup)
    metrics.update(parse_upstream(soup))

    graphite(metrics)


def parse_downstream(soup):

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
                logger.error(f"wut? {channel}")

    return downstream_metrics


def parse_upstream(soup):
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


def print_graphite(key, value, ts):
    pieces = value.partition(".")
    if value.isnumeric():
        print(f"{key} {value} {ts}")
    elif pieces[0].isnumeric() and pieces[2].isnumeric():
        print(f"{key} {value} {ts}")
    else:
        logger.info(f"NaN: {key}: {value}")


def graphite(data):
    now = datetime.now().timestamp()

    for metric, value in data.items():
        if type(value) == dict:
            for key, sub in value.items():
                subkey_name = key.lower().replace(" ", "_")
                print_graphite(f"{metric}_{subkey_name}", sub, now)
        else:
            print_graphite(metric, value, now)


if __name__ == "__main__":
    main()
