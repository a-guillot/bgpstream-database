# bgpstream-database

This program gathers BGP events from bgpstream.com and stores them into a
postgresql database using their
[Twitter account](https://twitter.com/bgpstream?lang=en).

## Twitter App Setup

Credentials are needed in order to be able to access Twitter's API.
The file [credentials.py](credentials.py) needs to be filled with your
Twitter's information.

## Database Management

The events are stored in a postgresql database.
This part describes how everything is structured and how one can create it.

### Database Structure

The collected events are organized into a database that's separated into these
tables:

* Outage
* Hijack
* Leak
* Leaker

The scripts that generate these tables can be found [here](sql/schema.sql).
However, the database needs to be created before the automatic generation of
the tables described above.

#### Outage table:

* `id`: a unique identifier that corresponds to the bgpstream.com id
* `start_time`: the time when the outage began
* `end_time`: the time when the outage ended (not always specified)
* `asn`: the number of the Autonomous System
* `as_name`: the name of the Autonomous System
* `number_of_prefixes`: the number of prefixes that have been affected by the
outage
* `percentage`: the percentage (between 0 and 1) of prefixes that have been
affected

The `PRIMARY KEY` is composed of the `id` field.

#### Hijack table:

* `id`: a unique identifier that corresponds to the bgpstream.com id
* `start_time`: the time when bgpstream.com detected the hijack
* `original_prefix`: the prefix that is being hijacked
* `original_asn`: the number of the Autonomous System that announced
`original_prefix`
* `original_as_name`: the name of the Autonomous System
* `hj_time`: the time when the hijack occurred
* `hj_prefix`: the prefix that contains or is a part of `original_prefix`.
* `hj_asn`: the hijacker's asn
* `hj_as_name`: the name of the hijacker's AS
* `hj_as_path`: the resulting as-path
* `number_of_peers`: the number of BGPMon peers that detected the hijack (and
not the number of peers that the AS possesses).

The `PRIMARY KEY` is composed of (id).

#### Leak table:

* `id`: a unique identifier that corresponds to the bgpstream.com id
* `start_time`: date at which the leak was detected
* `prefix`: the prefix that is being leaked
* `original_asn`: the original owner of the prefix
* `original_as_name`: the original owner's AS name
* `leaking_asn`: asn of the leaker
* `leaking_as_name`: the leaker's as name
* `as_path`: the new as-path after the leak
* `number_of_peers`: the number of BGPMon peers that detected the leak

#### Leaker table:

This table gives the list of autonomous systems that propagated the erroneous
information.

* `id`: unique auto-incremented identifier
* `asn`: the leaker's asn
* `as_name`: its name
* `leak`: the bgpstream.com id of the corresponding leak. Directly links to
  `leak.id`

### Creating the Database

This part will create a postgresql user and will grant it the necessary rights,
which means that it is only necessary to do it the first time.
`$USER` is the name of the user that is willing to access the database.

```sh
sudo -u postgres -i # switch to user postgres
psql -c 'CREATE USER $USER;' # create a database user
psql -c 'ALTER ROLE $USER superuser;' # dirty workaround to get the necessary rights
exit # switch back to $USER
createdb # create a database user named $USER (which is necessary to be recognized as such)
psql -c 'CREATE DATABASE bgpstream;'
```

### Connecting to the Database

```sh
psql
\c bgpstream
" SQL requests
```
