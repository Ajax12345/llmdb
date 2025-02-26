import mysql.connector, typing
import contextlib, csv, time
import collections, subprocess
import datetime, re, json, os
import random, io, concurrent.futures
import functools

#https://dev.mysql.com/doc/connector-python/en/connector-python-example-connecting.html
#https://dev.mysql.com/doc/refman/8.0/en/innodb-parameters.html

def DB_EXISTS(requires_db = True) -> typing.Callable:
    def main_f(f:typing.Callable) -> typing.Callable:
        def wrapper(self, *args, **kwargs) -> typing.Any:
            if self.cur is None:
                raise Exception('cursor is not open')
            
            if requires_db and self.database is None:
                raise Exception('no database has been specified')
            
            return f(self, *args, **kwargs)

        return wrapper

    return main_f

class MySQL:
    def __init__(self, host:str = "localhost", user:str = "root", 
                passwd:str = "Gobronxbombers2", database:typing.Union[str, None] = None,
                create_cursor:bool = True, buffered:bool = False) -> None:
        self.host, self.user = host, user
        self.passwd, self.database = passwd, database
        self.conn = mysql.connector.connect(
            host = self.host,
            user = self.user,
            passwd = self.passwd,
            database = self.database,
            allow_local_infile=True,
            consume_results=True
        )
        self.buffered = buffered
        self.stdout_f = None
        self.cur = None
        if create_cursor:
            self.new_cur()

    def set_log_file(self, f:typing.Any) -> None:
        self.stdout_f = f

    def new_cur(self) -> 'cursor':
        self.cur = self.conn.cursor(dictionary = True, buffered=self.buffered)
        return self.cur

    @DB_EXISTS()
    def status(self) -> typing.List[dict]:
        self.cur.execute('show global status')
        return [*self.cur]

    @DB_EXISTS(requires_db = False)
    def memory_size(self, metric:str = 'b') -> dict:
        """
        @metric
            b (bytes)
            mb
            gb
        """
        denom = {"b":"", "mb":"/ 1024 / 1024", "gb":"/ 1024 / 1024/ 1024"}[metric.lower()]
        self.cur.execute(f"""select table_schema db_name, round(sum(data_length + index_length){denom}, 3) size 
        from information_schema.tables group by table_schema;""")
        return {i['db_name']:float(i['size']) for i in self.cur}


    @DB_EXISTS(requires_db = False)
    def _metrics(self) -> dict:
        self.cur.execute('select name, count from information_schema.innodb_metrics where status="enabled" order by name;')
        return {i['name']:int(i['count']) for i in self.cur}

    @DB_EXISTS(requires_db = False)
    def metrics(self, total_time:int, interval:int = 5) -> list:
        total_metrics = collections.defaultdict(list)
        p = []
        while total_time > 0:
            m = self._metrics()
            p.append(m)
            for a, b in m.items():
                total_metrics[a].append(b)

            time.sleep(interval)
            total_time -= interval

        print(sum(p[0]!= i for i in p))
        return {a:sum(b)/len(b) if a in self.__class__.VALUE_METRICS else float(b[-1] - b[0])
            for a, b in total_metrics.items()}        

    @DB_EXISTS(requires_db = False)
    def use_db(self, db:str) -> None:
        self.database = db
        self.cur.execute(f'use {db}')

    @DB_EXISTS()
    def execute(self, *args, **kwargs) -> 'cursor':
        self.cur.execute(*args, **kwargs)
        return self.cur

    @DB_EXISTS()
    def get_tables(self) -> typing.Any:
        self.cur.execute("show tables")
        return [j for i in self.cur for j in i.values()]

    @DB_EXISTS()
    def get_columns_from_tbl(self, tbl:str) -> typing.List[dict]:
        self.cur.execute("""
        select t.table_schema, t.table_name, t.column_name, t.ordinal_position,
            s.index_schema, s.index_name, s.seq_in_index, s.index_type 
        from information_schema.columns t
        left join information_schema.statistics s on t.table_name = s.table_name
            and t.table_schema = s.table_schema 
            and lower(s.column_name) = lower(t.column_name)
        where t.table_schema = %s and t.table_name = %s
        order by t.ordinal_position""", [self.database, tbl])
        return [*self.cur]

    @DB_EXISTS()
    def get_columns_from_database(self) -> typing.List[dict]:
        self.cur.execute("""
        select t.table_schema, t.table_name, t.column_name, t.data_type, 
            t.character_maximum_length, t.ordinal_position,
            s.index_schema, s.index_name, s.seq_in_index, s.index_type 
        from information_schema.columns t
        left join information_schema.statistics s on t.table_name = s.table_name
            and t.table_schema = s.table_schema 
            and lower(s.column_name) = lower(t.column_name)
        where t.table_schema = %s
        order by t.table_schema, t.table_name, t.column_name, t.ordinal_position""", [self.database])
        return [*self.cur]

    @property
    @DB_EXISTS()
    def metric_count(self) -> int:
        self.cur.execute('select count(*) c from information_schema.innodb_metrics where status="enabled" order by name;')
        return self.cur.fetchone()['c']

    @property
    @DB_EXISTS()
    def db_column_count(self) -> int:
        self.cur.execute('select count(*) c from information_schema.columns t where t.table_schema = %s', [self.database])
        return self.cur.fetchone()['c']

    @DB_EXISTS()
    def get_indices(self, tbl:str) -> typing.List[dict]:
        self.cur.execute(f"""show index from {tbl}""")
        return [*self.cur]

    @DB_EXISTS(requires_db = False)
    def get_knobs(self) -> list:
        self.cur.execute("show variables where variable_name in ({})".format(', '.join(f"'{i}'" for i in self.__class__.KNOBS)))
        knobs = {i['Variable_name']:i['Value'] if not i['Value'].isdigit() else int(i['Value']) for i in self.cur}
        return [knobs[i] for i in sorted(self.__class__.KNOBS)]

    @DB_EXISTS(requires_db = False)
    def get_knobs_as_dict(self) -> dict:
        self.cur.execute("show variables where variable_name in ({})".format(', '.join(f"'{i}'" for i in self.__class__.KNOBS)))
        knobs = {i['Variable_name']:i['Value'] if not i['Value'].isdigit() else int(i['Value']) for i in self.cur}
        return {i:knobs[i] for i in sorted(self.__class__.KNOBS)}

    @DB_EXISTS(requires_db = False)
    def get_knobs_scaled(self, knob_activation_payload:dict) -> list:
        self.cur.execute("show variables where variable_name in ({})".format(', '.join(f"'{i}'" for i in self.__class__.KNOBS)))
        knobs = {i['Variable_name']:i['Value'] if not i['Value'].isdigit() else int(i['Value']) for i in self.cur}
        return [knobs[i]/knob_activation_payload.get(
                v:=self.__class__.KNOBS[i][1][1], v) 
            for i in sorted(self.__class__.KNOBS)]

    @classmethod
    def metrics_to_list(cls, metrics:dict) -> typing.List[int]:
        assert metrics, "metrics must contain data"
        return [metrics[i] for i in sorted(metrics)]

    @classmethod
    def col_indices_to_list(cls, cols:typing.List[dict]) -> typing.List:
        assert cols, "table must contain columns"
        return [int(i['INDEX_NAME'] is not None) for i in cols]
    
    @classmethod
    def activate_index_actor_outputs(cls, outputs:typing.List[typing.List[float]]) -> typing.List[typing.List[int]]:
        return [[int(j >= 0.5) for j in i] for i in outputs]

    @classmethod
    def activate_knob_actor_outputs(cls, output:typing.List[float], knob_activation_payload:dict) -> typing.Tuple[typing.List[int], dict]:
        def activate_knob(val:float, knob:str) -> int:
            val = min(max(0, val), 1)
            knob_type, val_range = cls.KNOBS[knob]
            if knob_type == 'integer':
                min_val, max_val, *_ = [knob_activation_payload.get(i, i) for i in val_range]
                return max(min_val, int(max_val*val))
                
                '''
                min_val, max_val, step = [knob_activation_payload.get(i, i) for i in val_range]
                a_v = max(min_val, int(max_val*val))
                start = min_val
                while a_v > start:
                    start += step

                final_v = min(start, max_val)
                
                if final_v == max_val:
                    final_v = int(final_v * 0.98)
            

                print(knob, a_v, int(final_v), max_val)
                return int(final_v)
                '''
            
            return val_range[min(max(0, int(len(val_range)*val)), len(val_range) - 1)]


        result = [activate_knob(val, knob) for val, knob in zip(output, cls.KNOBS)]
        return result, {a:b for a, b in zip(cls.KNOBS, result)} 


    @classmethod
    def used_index_lookup(cls, d:dict) -> typing.Iterator:
        if isinstance(d, dict):
            if 'table' in d:
                yield {'table_name':d['table'].get('table_name'),
                    'possible_keys':d['table'].get('possible_keys'),
                    'key':d['table'].get('key'),
                    'used_key_parts':d['table'].get('used_key_parts'),
                    'ref':d['table'].get('ref')}

            for a, b in d.items():
                yield from cls.used_index_lookup(b)

            return
        
        if isinstance(d, list):
            for i in d:
                yield from cls.used_index_lookup(i)

    @DB_EXISTS()
    def get_query_stats(self, query:str) -> dict:
        self.cur.execute(f'explain format = json {query}')
        data = json.loads(self.cur.fetchone()['EXPLAIN'])
        return {'cost':float(data['query_block']['cost_info']['query_cost'])}


    @DB_EXISTS()
    def apply_index_configuration(self, indexes:dict) -> None:
        col_state = self.get_columns_from_database()
        d = collections.defaultdict(dict)
        
        for i in col_state:
            d[i['TABLE_NAME']][i['COLUMN_NAME']] = i
        
        for a, b in d.items():
            for j, k in b.items():
                if j not in indexes.get(a, []) and k['INDEX_NAME'] is not None:
                    self.cur.execute(f"drop index {k['INDEX_NAME']} on {a}")
                    print('dropped non-match')

        for a, b in indexes.items():
            for j in b:
                if d[a][j]['INDEX_NAME'] is None:
                    if d[a][j]['DATA_TYPE'].lower() == 'text':
                        self.cur.execute(f'create index LLMDB_INDEX_{j} on {a}({j}({min(20, int(d[a][j]["CHARACTER_MAXIMUM_LENGTH"]))}))')

                    else:
                        self.cur.execute(f'create index LLMDB_INDEX_{j} on {a}({j})')
                else:
                    print('index already exists, skipping')
       
        self.commit() 

    @DB_EXISTS()
    def compute_index_storage(self) -> float:
        self.cur.execute('''
        SELECT database_name, table_name, index_name,
        ROUND(stat_value * @@innodb_page_size / 1024 / 1024, 2) size_in_mb
        FROM mysql.innodb_index_stats
        WHERE stat_name = 'size' AND index_name != 'PRIMARY'
        ORDER BY size_in_mb DESC;
        ''')
        return sum(i['size_in_mb'] for i in self.cur if i['index_name'] != 'GEN_CLUST_INDEX' and i['database_name'] == self.database)

    @DB_EXISTS()
    def index_storage_consumption(self) -> dict:
        self.cur.execute('''
        SELECT database_name, table_name, index_name,
        ROUND(stat_value * @@innodb_page_size / 1024 / 1024, 2) size_in_mb
        FROM mysql.innodb_index_stats
        WHERE stat_name = 'size' AND index_name != 'PRIMARY'
        ORDER BY size_in_mb DESC;
        ''')
        return {f'{i["table_name"]}.{i["index_name"].replace("LLMDB_INDEX_", "")}':float(i['size_in_mb']) for i in self.cur if i['index_name'] != 'GEN_CLUST_INDEX'}


    @DB_EXISTS()
    def drop_all_indices(self) -> None:
        for col_data in self.get_columns_from_database():
            
            if col_data['INDEX_NAME'] and col_data['INDEX_NAME'].lower().startswith('PRIMARY'.lower()):
                continue
            
            
            if col_data['INDEX_NAME'] is not None:
                if col_data['INDEX_NAME'].lower().startswith('PRIMARY'.lower()):
                    self.cur.execute(f'alter table {col_data["TABLE_NAME"]} drop primary key')

                else:
                    self.cur.execute(f'drop index {col_data["INDEX_NAME"]} on {col_data["TABLE_NAME"]}')


        self.commit()

    @DB_EXISTS()
    def apply_knob_configuration(self, knobs:dict) -> None:
        self.__exit__()
        subprocess.run([
            '/opt/homebrew/bin/mysql.server',
            'restart', *[f"--{a.replace('_', '-')}={b}" for a, b in knobs.items()]
        ], stdout = self.stdout_f)
        self.conn = mysql.connector.connect(
            host = self.host,
            user = self.user,
            passwd = self.passwd,
            database = self.database
        )
        self.new_cur()
        return [knobs[i] for i in sorted(self.__class__.KNOBS)]

    @DB_EXISTS()
    def start_mysql_server(self) -> None:
        subprocess.run([
            '/opt/homebrew/bin/mysql.server',
            'start'
        ], stdout = self.stdout_f)

    @DB_EXISTS()
    def reset_knob_configuration(self) -> typing.List[float]:
        return self.apply_knob_configuration(self.__class__.KNOB_DEFAULTS)

    @DB_EXISTS()
    def default_selected_action(self, knob_activation_payload:dict) -> typing.List[float]:
        _ = self.__class__
        return [_.KNOB_DEFAULTS[i]/knob_activation_payload.get(_.KNOBS[i][-1][1], 
                    _.KNOBS[i][-1][1]) 
            for i in _.KNOBS]

    @DB_EXISTS()
    def get_knob_value(self, knob:str) -> dict:
        self.cur.execute(f'select @@global.{knob} knob')
        return self.cur.fetchone()['knob']

    @DB_EXISTS()
    def dqn_knob_actions(self) -> typing.List[list]:
        return [j for i in sorted(self.__class__.KNOBS) \
            for j in [(i, self.__class__.KNOBS[i][-1][-1], 3), 
                (i, -1*self.__class__.KNOBS[i][-1][-1], 1)]]

   

    def commit(self) -> None:
        self.conn.commit()

    def __enter__(self) -> 'MySQL':
        return self

    def __exit__(self, *_) -> None:
        if self.cur is not None:
            with contextlib.suppress():
                self.cur.close()

        self.conn.close()

class MySQL_CC(MySQL):
    @DB_EXISTS()
    def apply_knob_configuration(self, knobs:dict) -> None:
        with open('/etc/mysql/my.cnf') as f:
            config = f.read()
            config = re.sub('(\w+)\=(\w+)', lambda x:f'{x.group(1)}={knobs[x.group(1)] if x.group(1) in knobs else x.group(2)}', config)

        with open('/etc/mysql/my.cnf', 'w') as f:
            f.write(config)
            
        self.__exit__()
        subprocess.run(['sudo', 'service', 
        'mysql', 'restart'], stdout = self.stdout_f)
        self.conn = mysql.connector.connect(
            host = self.host,
            user = self.user,
            passwd = self.passwd,
            database = self.database
        )
        self.new_cur()
        return [knobs[i] for i in sorted(self.__class__.KNOBS)]


if __name__ == '__main__':
    with MySQL(database = "tpch") as conn:
        #conn.apply_index_configuration({})
        #print(conn.compute_index_storage())
        
        conn.apply_index_configuration({})
        '''
        conn.apply_index_configuration({'orders': ['o_orderkey'], 'customer': ['c_custkey', 'c_name', 'c_nationkey'], 'part': ['p_partkey', 'p_brand']})
        
        cols = {i['TABLE_NAME'] for i in conn.get_columns_from_database()}
        for i in cols:
            print(i, [j['Key_name'] for j in conn.get_indices(i)])
        
        print(conn.index_storage_consumption())
        #print([conn.compute_index_storage() for _ in range(5)])
        '''
        
        