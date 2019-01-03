#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2018, Kevin Tarrant (@ktarrant)
#
# Distributed under the terms of the MIT License.
#
# The full license is in the file LICENSE.txt, distributed with this software.
#
# REFERENCES:
# http://ipython.org/ipython-doc/rel-0.13.2/development/coding_guide.html
# https://www.python.org/dev/peps/pep-0008/
# -----------------------------------------------------------------------------
"""Methods for loading, caching, and saving IEX finance data
"""

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# stdlib imports -------------------------------------------------------
import logging
import datetime
from collections import OrderedDict

# Third-party imports -----------------------------------------------
import pandas as pd
import requests

# Our own imports ---------------------------------------------------

# -----------------------------------------------------------------------------
# GLOBALS
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------------------
URL_CHART = "https://api.iextrading.com/1.0/stock/{symbol}/chart/{range}"
URL_EARNINGS = "https://api.iextrading.com/1.0/stock/{symbol}/earnings"
URL_DIVIDENDS = (
    "https://api.iextrading.com/1.0/stock/{symbol}/dividends/{range}"
)
# -----------------------------------------------------------------------------
# LOCAL UTILITIES
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)

parsedate = lambda d: datetime.datetime.strptime(d, "%Y-%m-%d")
""" Parses a date like 2018-02-01 """


# -----------------------------------------------------------------------------
# CLASSES
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# FUNCTIONS
# -----------------------------------------------------------------------------

# ESTIMATION UTILS  -----------------------------------------
def estimate_next(prev_dates):
    """
    Estimates the most likely next date based on previous dates
    Args:
        prev_dates (list(datetime.datetime)): List of previous dates to use
            for our guesses

    Returns:
        datetime.datetime: Best guess for next event
    """
    today = datetime.datetime.today()
    guesses = [i + datetime.timedelta(days=365) for i in prev_dates]
    guesses += [i + datetime.timedelta(days=730) for i in prev_dates]
    try:
        return min(i for i in guesses
                   if i + datetime.timedelta(days=365) > today)
    except ValueError:
        return None


# WEB LOADERS       -----------------------------------------
def load_historical(symbol, range="1m", cache=False):
    '''
    Loads historical data from IEX Finance

    Args:
        symbol (str): stock ticker to look up
        range (str): lookback period
        force (bool): if True, will skip checking for cache file

    Returns:
        pd.DataFrame: cached or loaded DataFrame
    '''
    url = URL_CHART.format(symbol=symbol, range=range)
    logger.info("Loading: '{}'".format(url))
    df = pd.DataFrame(requests.get(url).json())
    return df

def load_earnings(symbol):
    '''
    Loads earnings data from IEX Finance

    Args:
        symbol (str): stock ticker to look up

    Returns:
        pd.DataFrame: loaded DataFrame
    '''
    url = URL_EARNINGS.format(symbol=symbol)
    logger.info("Loading: '{}'".format(url))
    result = requests.get(url).json()
    df = pd.DataFrame(result["earnings"])
    df[["EPSReportDate", "fiscalEndDate"]] = (
        df[["EPSReportDate", "fiscalEndDate"]].applymap(parsedate))
    return df.set_index("EPSReportDate")

def load_dividends(symbol, range='1y'):
    '''
    Loads dividends data from IEX Finance

    Args:
        symbol (str): stock ticker to look up
        range (str): lookback period

    Returns:
        pd.DataFrame: loaded DataFrame
    '''
    url = URL_DIVIDENDS.format(symbol=symbol, range=range)
    logger.info("Loading: '{}'".format(url))
    df = pd.DataFrame(requests.get(url).json())
    if "exDate" in df.columns:
        date_cols = ["declaredDate", "exDate", "paymentDate", "recordDate"]
        df[date_cols] = df[date_cols].applymap(parsedate)
        return df.set_index("exDate")
    else:
        return None

def load_calendar(symbol):
    '''
    Loads calendar data from IEX Finance

    Args:
        symbol (str): stock ticker to look up

    Returns:
        pd.DataFrame: cached or loaded DataFrame
    '''

    today = datetime.date.today()

    earnings = load_earnings(symbol)
    dividends = load_dividends(symbol)
    if earnings is not None:
        last_reportDate = max(earnings.index)
        next_reportDate = estimate_next(earnings.index)
    else:
        last_reportDate = None
        next_reportDate = None

    if dividends is not None:
        last_exDate = max(dividends.index)
        last_dividend = dividends.loc[last_exDate, "amount"]
        next_exDate = estimate_next(earnings.index)
    else:
        last_exDate = None
        last_dividend = None
        next_exDate = None

    calendar = pd.Series(OrderedDict([
        ("lastEPSReportDate", last_reportDate),
        ("nextEPSReportDate", next_reportDate),
        ("lastExDate", last_exDate),
        ("lastDividend", last_dividend),
        ("nextExDate", next_exDate),
    ]))
    return calendar

# ARGPARSE CONFIGURATION  -----------------------------------------
def add_subparser_historical(subparsers):
    """
    Loads historical data from IEX Finance

    Args:
        subparsers: subparsers to add to

    Returns:
        Created subparser object
    """
    def cmd_hist(args):
        return load_historical(args.symbol, args.range, args.cache)

    hist_parser = subparsers.add_parser("historical", description="""
    loads historical OHLC data for a stock symbol 
    """)
    hist_parser.add_argument("symbol", type=str, help="stock ticker to look up")
    hist_parser.add_argument("-r", "--range", type=str, default="1m",
                             help="lookback period, default: 1m")
    hist_parser.set_defaults(func=cmd_hist)
    return hist_parser


def add_subparser_calendar(subparsers):
    """
    Loads calendar (earnings and dividend) data from IEX Finance

    Args:
        args: parsed arguments object containing arguments for the
            load_earnings method

    Returns:
        pd.DataFrame: cached or loaded DataFrame
    """
    def cmd_calendar(args):
        return load_calendar(args.symbol, args.cache)
    earnings_parser = subparsers.add_parser("calendar", description="""
    loads calendar earnings and dividend data with estimates for next event
    """)
    earnings_parser.add_argument("symbol", type=str,
                                 help="stock ticker to look up")
    earnings_parser.set_defaults(func=cmd_calendar)
    return earnings_parser

# -----------------------------------------------------------------------------
# RUNTIME PROCEDURE
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="""
    Loads historical data locally or from IEX if necessary and caches it.
    """)
    parser.add_argument("-c", "--cache", action="store_true",
                        help="cache loaded data")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="use verbose logging")

    subparsers = parser.add_subparsers()

    add_subparser_historical(subparsers)
    add_subparser_calendar(subparsers)

    args = parser.parse_args()

    # configure logging
    logLevel = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=logLevel)
    df = args.func(args)
    print(df)