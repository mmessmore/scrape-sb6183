# scrape-sb6183

Scrape Arris SB6183 metrics from the web page and print Graphite-formatted
results to SDTOUT.

This is suited for an 'exec' type Telegraf plugin or can be piped to netcat
to feed to Graphite itself.

Logs/errors go to STDERR to not interfere with automation output.

The HTML of the page is completely broken, so this is an ugly hack that may
break for different versions.  Tested against D30CM-
OSPREY-2.4.0.1-GA-02-NOSH

This may also work for other models.

See `./scrape.py --help` for usage info.

# License

This is licensed under the [MIT License](./LICENSE)
