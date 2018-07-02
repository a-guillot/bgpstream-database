#!/usr/bin/python3.5

###############################################################################
# Imports

import argparse  # Argument parsing
import requests  # Webpage requests
import re       # Regular expressions
import psycopg2  # Postgresql
import json     # JSON format parsing

# BGPStream Twitter mining
import tweepy
from tweepy import Stream
from tweepy import OAuthHandler
from tweepy.streaming import StreamListener

# Twitter app credentials
from credentials import *

# General utility
import sys
import datetime
import os
from pprint import pprint

###############################################################################
# Argument Parsing


def get_parser():
    # Get parser for command line arguments
    parser = argparse.ArgumentParser(
        description="This is a BGP Monitoring program"
    )
    parser.add_argument('-x', '--debug', action='store_true',
                        help='print debug info')
    parser.add_argument('-c', '--clear-database', action='store_true',
                        help='reset the database')
    parser.add_argument('-u', '--username', action='store', default='database',
                        type=str, help='specify the username of the database. default=root')
    parser.add_argument('-d', '--database', action='store',
                        default='bgpstream', help='specify the name of the database. '
                        'default=bgpstream')

    return parser


###############################################################################
# Database

class Database():
    """ Creates and manages a postgresql database """

    def __init__(self, name, user, clear):
        """ Initializes the database connection and clears it if the option -c
            is specified.
        """

        # Connect to the database
        self.connection = psycopg2.connect("dbname='{}' user='{}' "
                                           "password='' host=''".format(name, user))

        # [optional] clear it
        if clear:
            self.clear()

    ###########################################################################

    def clear(self):
        """ Deletes every table of the database """

        # Create a cursor to query the db
        cursor = self.connection.cursor()

        # Delete all tables (by default every table is in public)
        cursor.execute("DROP SCHEMA IF EXISTS public CASCADE;")

        # Reset the schema
        cursor.execute('CREATE SCHEMA public;')

        # Commit the result
        self.connection.commit()

    ###########################################################################

    def fill(self):
        """ Fills the database with every event described on bgpstream.com that
            has not been added to the database yet
        """

        #######################################################################

        def check(database):
            """ Check if every table from sql/table_names.txt exists
                Returns: True if they all exist, else False
            """

            table_names = [line.rstrip()
                           for line in open('sql/table_names.txt')]

            cursor = database.connection.cursor()

            # If a table is missing then an exception will be raised
            try:
                for name in table_names:
                    cursor.execute('SELECT 1 FROM {}'.format(name))
            except psycopg2.ProgrammingError:
                database.connection.rollback()  # Reset the transaction
                return False

            return True

        #######################################################################

        def create_tables(database):
            """ Creates the DB tables by executing the sql/schema.sql file
                Returns: nothing
            """

            cursor = database.connection.cursor()

            # Create tables from the file 'sql/table_names.txt'
            cursor.execute(open('sql/schema.sql').read())

            # Commit the result
            database.connection.commit()

        #######################################################################

        def get_last_tweet_info(account='bgpstream'):
            """ Look for the last tweet posted by @bgpstream
                Returns: number of the last bgpstream event
            """

            # Twitter authentication
            auth = tweepy.OAuthHandler(twitterConsumerKey,
                                       twitterConsumerSecret)
            auth.set_access_token(twitterAccessToken, twitterAccessSecret)
            api = tweepy.API(auth)

            # Retrieve last tweet from timeline
            last_tweet = api.user_timeline(screen_name=account, count=1)[0]

            # Extract bgpstream number from the last tweet
            event_number = int(last_tweet.entities
                               ['urls'][0]['expanded_url'].split('/')[-1])

            return event_number

        #######################################################################

        def get_latest_database_entry(database, id_columns={'Leak': 'id'}):
            """ Get the highest id from the 'Leak' table. This is because
                tweets
                Returns: the highest id contained in the DB or 0
            """

            cursor = database.connection.cursor()

            # Initialize to smallest id possible
            res = 0

            # Get the highest date from tables specified in 'time_columns'
            for table_name, column_name in id_columns.items():
                try:
                    cursor.execute("SELECT MAX({}) FROM {};".format(column_name,
                                                                    table_name))  # Get the highest value, or None if empty
                    temp = cursor.fetchone()[0]

                    # Max between res and this table's value
                    res = temp if (temp is not None and temp > res) else res
                except psycopg2.ProgrammingError:
                    database.connection.rollback()

            return res

        #######################################################################

        def save_events(database, last_event_number, latest_entry_number):
            """ Starting from the bgpstream event 'last_event_number', iterate
                over  every event until 'latest_entry_number' is reached
            """

            ###################################################################

            def bgpstream_page_iterator(first_event, threshold,
                                        url='https://bgpstream.com/event/', dir='html'):
                """ Yields the html code of 'url'/x, where x is the event
                    number. The event number goes from 'first_event" to
                    threshold.
                    Returns:
                        the page code
                        the html code
                """

                # Object to request web pages
                s = requests.session()

                # Iterate from 'first_event' to 'threshold':
                current_event = first_event
                while (current_event >= threshold):
                    # Check if file is already stored offline
                    if os.path.isfile('{}/{}.txt'.format(dir, current_event)):
                        # Return its content
                        with open('{}/{}.txt'.format(dir, current_event)) as f:
                            yield current_event, f.readlines()
                    else:
                        # Download the page
                        page = s.get(url + str(current_event))

                        # Check for Integrity
                        if page.status_code != 500:

                            # Save it locally
                            with open(
                                    '{}/{}.txt'.format(dir, current_event),
                                    'a') as f:
                                f.write(page.text)

                            # Return the result
                            yield current_event, page.text

                    current_event -= 1

            ###################################################################

            def parse_html_page(page_number, page):
                """ Extracts the information that will be inserted inside the
                    database
                    Return:
                        type: the event type (i.e. outage or hijack)
                        columns: a dictionary containing {column_name: value}
                """

                ###############################################################

                def clean_html(raw_html):
                    cleanr = re.compile('<.*?>')
                    cleantext = re.sub(cleanr, '', raw_html)
                    return cleantext

                ###############################################################

                # Dict containing the values to be inserted inside the
                # database with the format {column_name: value, ...}
                columns = {}

                # Determine page type
                type = ''
                type += 'Outage' if ('outage' in page) else ''
                type += 'Hijack' if ('hijack' in page) else ''
                type += 'Leak' if ('Leak' in page) else ''

                queries = {}
                queries[type] = {}

                # the id becomes the bgpstream event number
                columns['id'] = page_number

                # Variables necessary when one needs to analyze multiple lines
                is_hj_as_name = False
                is_leaker = False
                sub_query_columns = {'leak': [], 'asn': [], 'as_name': []}

                # for each line in the html file
                for line in page.split('\n'):
                    #
                    if type == 'Outage':
                        if "Start time:" in line:
                            columns['start_time'] = line.split()[2] + \
                                " " + line.split()[3]
                        elif "End time:" in line:
                            columns['end_time'] = line.split()[2] + \
                                " " + line.split()[3]
                        elif "we detected an outage" in line:
                            # Split cases where ASN is mentioned or when the
                            # country is mentioned
                            if "ASN" in line:
                                columns['asn'] = int(
                                    line.split('ASN')[1].split('(')[0]
                                )
                                columns['as_name'] = line.split(
                                    '(')[1].split(')')[0]
                            else:
                                columns['asn'] = 0
                                columns['as_name'] = line.split('for '
                                                                '')[1].split()[0]
                        elif "Number of Prefixes" in line:
                            columns['number_of_prefixes'] = int(
                                line.split(':')[1].split('(')[0]
                            )
                            columns['percentage'] = int(
                                line.split('(')[1].split('%')[0]
                            ) / 100
                    #
                    elif type == 'Leak':
                        if "Start time:" in line:
                            columns['start_time'] = line.split()[2] + \
                                " " + line.split()[3]
                        if 'Leaked prefix:' in line:
                            tmp = line.split(': ')[1]
                            columns['prefix'] = tmp.split()[0]
                            columns['original_asn'] = int(
                                tmp.split('AS')[1].split()[0]
                            )
                            tmp = tmp.split('(')[1].split(')')[0].split()[1:]
                            columns['original_as_name'] = (
                                ' '.join(tmp)
                            )
                        if 'Leaked by' in line:
                            columns['leaking_asn'] = int(
                                line.split('AS')[1].split()[0]
                            )
                            columns['leaking_as_name'] = clean_html(
                                ' '.join(line.split('AS')[1].split()[1:])
                            )
                        if 'Example AS path:' in line:
                            columns['as_path'] = clean_html(
                                line.split(': ')[1]
                            )[:-1]
                        if 'Number of BGPMon peers' in line:
                            columns['number_of_peers'] = int(
                                clean_html(line.split(': ')[1])
                            )
                        if 'Leaked To:' in line:
                            is_leaker = True
                            sub_query_columns['leak'] = page_number
                        if '<li>' in line and is_leaker:
                            sub_query_columns['asn'].append(
                                clean_html(line.split()[0])
                            )
                            sub_query_columns['as_name'].append(
                                line.split('(')[1].split(')')[0]
                            )
                        if '</td>' in line and is_leaker:
                            if 'Leaker' not in queries:
                                queries['Leaker'] = {}
                            for key, value in sub_query_columns.items():
                                queries['Leaker'][key] = value

                            is_leaker = False
                    #
                    elif type == 'Hijack':
                        if "Start time:" in line:
                            columns['start_time'] = line.split()[2] + \
                                " " + line.split()[3]
                        if 'Expected prefix:' in line:
                            columns['original_prefix'] = clean_html(
                                line.split(': ')[1]
                            )
                        if 'Expected ASN:' in line:
                            tmp = line.split(': ')[1]
                            columns['original_asn'] = int(tmp.split()[0])

                            is_hj_as_name = True
                        if '(' in line and is_hj_as_name:
                            columns['original_as_name'] = line.split(
                                '(')[1].split(')')[0]
                            is_hj_as_name = False
                        if 'But beginning at' in line:
                            columns['hj_time'] = (
                                line.split()[3] + " " + line.split()[4]
                            )
                        if 'Detected advertisement:' in line:
                            columns['hj_prefix'] = clean_html(
                                line.split(': ')[1]
                            )
                        if 'Detected Origin ASN' in line:
                            columns['hj_asn'] = int(line.split()[3])
                            is_hj_as_name = True

                        if '(' in line and is_hj_as_name:
                            columns['hj_as_name'] = clean_html(
                                line.split('(')[1].split(')')[0]
                            )
                            is_hj_as_name = False
                        if 'Detected AS Path' in line:
                            columns['hj_as_path'] = clean_html(
                                line.split('Path ')[1]
                            )
                        if 'Detected by number of BGPMon' in line:
                            columns['number_of_peers'] = int(
                                clean_html(line.split(':')[1])
                            )

                queries[type] = columns
                return queries

            ###################################################################

            def query_iterator(queries):
                """ Returns the next query to be inserted inside the database.
                    Necessary to extract queries from arrays of values
                """

                ##############################################################

                def is_empty(dictionary):
                    """ Tests if every list contained in this dictionary are
                        empty
                    """

                    for key, value in dictionary.items():
                        if isinstance(value, list) and len(value) != 0:
                            return False
                    else:
                        return True

                ##############################################################

                for type, columns in queries.items():
                    values_list = {}
                    query = {}

                    for key, value in columns.items():
                        if isinstance(value, list):
                            for v in value:
                                values_list[key] = value

                    # Case where the query is not a complicated one
                    if not values_list:
                        yield type, columns
                        continue

                    while not is_empty(values_list):
                        for key, value in columns.items():
                            if key not in values_list:
                                query[key] = value
                            else:
                                query[key] = values_list[key][0]
                                values_list[key].pop(0)

                        yield type, query

            ###################################################################

            def insert_event_into_database(database, table_name, columns):
                """ The table name is provided by the type and the column names
                    and values are provided by 'columns', which means that the
                    'INSERT INTO' is generic
                """

                cursor = database.connection.cursor()

                # Formatting values
                keys = ""
                values = ""
                for key, value in columns.items():
                    keys += key + ', '
                    values += "'" + str(value).replace("'", "") + "', "

                # Removing trailing characters
                keys = keys[:-2]
                values = values[:-2]

                # Inserting
                if DEBUG:
                    print("INSERT INTO {} ({}) VALUES ({});".format(type,
                                                                    keys, values))
                cursor.execute("INSERT INTO {} ({}) VALUES ({});".format(type,
                                                                         keys, values))

            ###################################################################

            # For each html page describing an event that is not inside the
            # database yet:
            for page_number, page in bgpstream_page_iterator(last_event_number,
                                                             latest_entry_number):
                # Extract the type and the columns of the html page
                queries = parse_html_page(page_number, page)

                for type, columns in query_iterator(queries):
                    insert_event_into_database(database, type, columns)
                database.connection.commit()

        #######################################################################

        # If a table is missing then recreate all tables
        if not check(self):
            self.clear()
            create_tables(self)

        # Find the latest bgpstream.com event number with the last tweet sent
        # by @bgpstream
        last_event_number = get_last_tweet_info()

        # Find the highest event number in the database to find the last tweet
        # that had been added
        latest_entry_number = get_latest_database_entry(self)

        # Save the new events inside the database
        save_events(self, last_event_number, latest_entry_number)

    ###########################################################################

    def __repr__(self):
        return ('Database')


###############################################################################

if __name__ == "__main__":
    # Create a parser
    parser = get_parser()

    # Parse arguments
    args = parser.parse_args()
    clear_database = args.clear_database
    db_username = args.username
    db_name = args.database

    global DEBUG
    DEBUG = args.debug

    # Create html directory
    if not os.path.exists('html/'):
        os.makedirs('html/')

    # Preparing the database, and resetting it if clear_database is true
    database = Database(db_name, db_username, clear_database)

    database.fill()  # Fill the database with tweets
