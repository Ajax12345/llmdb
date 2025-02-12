-- nation
CREATE TABLE IF NOT EXISTS nation (
  `n_nationkey`  INT,
  `n_name`       CHAR(25),
  `n_regionkey`  INT,
  `n_comment`    VARCHAR(152),
  `n_dummy`      VARCHAR(10),
  PRIMARY KEY (`n_nationkey`));

update nation set n_comment = "";
-- region
CREATE TABLE IF NOT EXISTS region (
  `r_regionkey`  INT,
  `r_name`       CHAR(25),
  `r_comment`    VARCHAR(152),
  `r_dummy`      VARCHAR(10),
  PRIMARY KEY (`r_regionkey`));

update region set r_comment = "";

-- supplier
CREATE TABLE IF NOT EXISTS supplier (
  `s_suppkey`     INT,
  `s_name`        CHAR(25),
  `s_address`     VARCHAR(40),
  `s_nationkey`   INT,
  `s_phone`       CHAR(15),
  `s_acctbal`     DECIMAL(15,2),
  `s_comment`     VARCHAR(101),
  `s_dummy` varchar(10),
  PRIMARY KEY (`s_suppkey`));

update supplier set s_comment = "";
-- customer
CREATE TABLE IF NOT EXISTS customer (
  `c_custkey`     INT,
  `c_name`        VARCHAR(25),
  `c_address`     VARCHAR(40),
  `c_nationkey`   INT,
  `c_phone`       CHAR(15),
  `c_acctbal`     DECIMAL(15,2),
  `c_mktsegment`  CHAR(10),
  `c_comment`     VARCHAR(117),
  `c_dummy`       VARCHAR(10),
  PRIMARY KEY (`c_custkey`));

update customer set c_comment = "";
-- part
CREATE TABLE IF NOT EXISTS part (
  `p_partkey`     INT,
  `p_name`        VARCHAR(55),
  `p_mfgr`        CHAR(25),
  `p_brand`       CHAR(10),
  `p_type`        VARCHAR(25),
  `p_size`        INT,
  `p_container`   CHAR(10),
  `p_retailprice` DECIMAL(15,2) ,
  `p_comment`     VARCHAR(23) ,
  `p_dummy`       VARCHAR(10),
  PRIMARY KEY (`p_partkey`));

update part set p_comment = "";

-- partsupp
CREATE TABLE IF NOT EXISTS partsupp (
  `ps_partkey`     INT,
  `ps_suppkey`     INT,
  `ps_availqty`    INT,
  `ps_supplycost`  DECIMAL(15,2),
  `ps_comment`     VARCHAR(199),
  `ps_dummy`       VARCHAR(10),
  PRIMARY KEY (`ps_partkey`));

update partsupp set ps_comment = "";
-- orders
CREATE TABLE IF NOT EXISTS orders (
  `o_orderkey`       INT,
  `o_custkey`        INT,
  `o_orderstatus`    CHAR(1),
  `o_totalprice`     DECIMAL(15,2),
  `o_orderdate`      DATE,
  `o_orderpriority`  CHAR(15),
  `o_clerk`          CHAR(15),
  `o_shippriority`   INT,
  `o_comment`        VARCHAR(79),
  `o_dummy`          VARCHAR(10),
  PRIMARY KEY (`o_orderkey`));

update orders set o_comment = "";

-- lineitem
CREATE TABLE IF NOT EXISTS lineitem (
  `l_orderkey`    INT,
  `l_partkey`     INT,
  `l_suppkey`     INT,
  `l_linenumber`  INT,
  `l_quantity`    DECIMAL(15,2),
  `l_extendedprice`  DECIMAL(15,2),
  `l_discount`    DECIMAL(15,2),
  `l_tax`         DECIMAL(15,2),
  `l_returnflag`  CHAR(1),
  `l_linestatus`  CHAR(1),
  `l_shipdate`    DATE,
  `l_commitdate`  DATE,
  `l_receiptdate` DATE,
  `l_shipinstruct` CHAR(25),
  `l_shipmode`    CHAR(10),
  `l_comment`     VARCHAR(44),
  `l_dummy`       VARCHAR(10));

update lineitem  set l_comment = "";

-- /Users/jamespetullo/Downloads/TPC_H_official/dbgen/customer.tbl
-- /Users/jamespetullo/Downloads/TPC_H_official/dbgen/lineitem.tbl
-- /Users/jamespetullo/Downloads/TPC_H_official/dbgen/nation.tbl
-- /Users/jamespetullo/Downloads/TPC_H_official/dbgen/orders.tbl
-- /Users/jamespetullo/Downloads/TPC_H_official/dbgen/part.tbl
-- /Users/jamespetullo/Downloads/TPC_H_official/dbgen/partsupp.tbl
-- /Users/jamespetullo/Downloads/TPC_H_official/dbgen/region.tbl
-- /Users/jamespetullo/Downloads/TPC_H_official/dbgen/supplier.tbl

LOAD DATA LOCAL INFILE '/Users/jamespetullo/Downloads/TPC_H_official/dbgen/region.tbl'     INTO TABLE region     FIELDS TERMINATED BY '|';
LOAD DATA LOCAL INFILE '/Users/jamespetullo/Downloads/TPC_H_official/dbgen/nation.tbl'     INTO TABLE nation     FIELDS TERMINATED BY '|';
LOAD DATA LOCAL INFILE '/Users/jamespetullo/Downloads/TPC_H_official/dbgen/customer.tbl' INTO TABLE customer   FIELDS TERMINATED BY '|';
LOAD DATA LOCAL INFILE '/Users/jamespetullo/Downloads/TPC_H_official/dbgen/supplier.tbl' INTO TABLE supplier   FIELDS TERMINATED BY '|';
LOAD DATA LOCAL INFILE '/Users/jamespetullo/Downloads/TPC_H_official/dbgen/part.tbl'         INTO TABLE part       FIELDS TERMINATED BY '|';
LOAD DATA LOCAL INFILE '/Users/jamespetullo/Downloads/TPC_H_official/dbgen/partsupp.tbl' INTO TABLE partsupp   FIELDS TERMINATED BY '|';
LOAD DATA LOCAL INFILE '/Users/jamespetullo/Downloads/TPC_H_official/dbgen/orders.tbl'     INTO TABLE orders     FIELDS TERMINATED BY '|';
LOAD DATA LOCAL INFILE '/Users/jamespetullo/Downloads/TPC_H_official/dbgen/lineitem.tbl' INTO TABLE lineitem   FIELDS TERMINATED BY '|';