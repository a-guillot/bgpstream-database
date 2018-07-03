-------------------------------------------------------------------------------
-- Database Schema
-------------------------------------------------------------------------------

------------------------------------------------------------------------------
-- Outage 
-----------------------------------------------------------------------------

CREATE TABLE Outage (
  id INTEGER,
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  asn INTEGER,
  as_name TEXT,
  number_of_prefixes SMALLINT,
  percentage REAL,

  PRIMARY KEY (id)
);

------------------------------------------------------------------------------
-- Leak
-----------------------------------------------------------------------------

CREATE TABLE Leak (
  id INTEGER,
  start_time TIMESTAMP,
  prefix INET,
  original_asn INTEGER,
  original_as_name TEXT,
  leaking_asn INTEGER,
  leaking_as_name TEXT,
  as_path TEXT,
  number_of_peers SMALLINT,

  PRIMARY KEY (id)
);

------------------------------------------------------------------------------
-- Leakers
-----------------------------------------------------------------------------

CREATE TABLE Leaker (
  id SERIAL,
  asn INTEGER,
  as_name TEXT,
  leak INTEGER,

  PRIMARY KEY (id),
  FOREIGN KEY (leak) REFERENCES Leak (id)
);

------------------------------------------------------------------------------
-- Hijack
-----------------------------------------------------------------------------

CREATE TABLE Hijack (
  id INTEGER,
  start_time TIMESTAMP,
  original_prefix INET,
  original_asn INTEGER,
  original_as_name TEXT,
  hj_time TIMESTAMP,
  hj_prefix INET,
  hj_asn INTEGER,
  hj_as_name TEXT,
  hj_as_path TEXT,
  number_of_peers SMALLINT,

  PRIMARY KEY (id)
);

