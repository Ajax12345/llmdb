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
    VALUE_METRICS = [
        'lock_deadlocks', 'lock_timeouts', 'lock_row_lock_time_max',
        'lock_row_lock_time_avg', 'buffer_pool_size', 'buffer_pool_pages_total',
        'buffer_pool_pages_misc', 'buffer_pool_pages_data', 'buffer_pool_bytes_data',
        'buffer_pool_pages_dirty', 'buffer_pool_bytes_dirty', 'buffer_pool_pages_free',
        'trx_rseg_history_len', 'file_num_open_files', 'innodb_page_size'
    ]
    ALL_KNOBS = {
        ###'skip_name_resolve': ['enum', ['OFF', 'ON']],
        'table_open_cache': ['integer', [1, 10240, 512]],
        #'max_connections': ['integer', [1100, 100000, 80000]],
        'innodb_buffer_pool_size': ['integer', [5242880, 'memory_size', 'memory_size']],
        'innodb_buffer_pool_instances': ['integer', [1, 64, 8]],
        #1
        #'innodb_log_files_in_group': ['integer', [2, 100, 2]],
        #1
        #'innodb_log_file_size' (Depreciated): ['integer', [134217728, 5497558138, 15569256448]],
        'innodb_purge_threads': ['integer', [1, 32, 1]],
        'innodb_read_io_threads': ['integer', [1, 64, 12]],
        'innodb_write_io_threads': ['integer', [1, 64, 12]],
        #3
        #'max_binlog_cache_size': ['integer', [4096, 4294967296, 18446744073709547520]],
        #'binlog_cache_size': ['integer', [4096, 4294967296, 18446744073709547520]],
        #'max_binlog_size': ['integer', [4096, 1073741824, 1073741824]],
        ###'innodb_adaptive_flushing_lwm': ['integer', [0, 70, 10]],
        #4
        #'innodb_flush_log_at_timeout': ['integer', [1, 2700, 1]],
        #'innodb_max_purge_lag': ['integer', [0, 4294967295, 0]],
        ###'innodb_old_blocks_pct': ['integer', [5, 95, 37]],
        'innodb_read_ahead_threshold': ['integer', [0, 64, 56]],
        #2
        #'innodb_replication_delay': ['integer', [0, 10000, 0]],
        #'innodb_rollback_segments': ['integer', [1, 128, 128]],
        'innodb_sync_array_size': ['integer', [1, 1024, 1]],
        'innodb_sync_spin_loops': ['integer', [0, 100, 30]],
        'innodb_thread_concurrency': ['integer', [0, 100, 0]],
        #1
        #'lock_wait_timeout': ['integer', [1, 31536000, 31536000]],
        ###'metadata_locks_cache_size': ['integer', [1, min(memory_size, 1048576), 1024]],
        #'metadata_locks_hash_instances': ['integer', [1, 1024, 8]],
        #2
        #'binlog_order_commits': ['boolean', ['OFF', 'ON']],
        #'innodb_adaptive_flushing': [' boolean', ['OFF', 'ON']],
        'innodb_adaptive_hash_index': ['boolean', ['ON', 'OFF']],
        #1
        #'innodb_autoextend_increment': [' integer', [1, 1000, 64]],  # mysql 5.6.6: 64, mysql5.6.5: 8
        ###'innodb_buffer_pool_dump_at_shutdown': ['boolean', ['OFF', 'ON']],
        ###'innodb_buffer_pool_load_at_startup': ['boolean', ['OFF', 'ON']],
        ###'innodb_concurrency_tickets': ['integer', [1, 50000, 5000]],  # 5.6.6: 5000, 5.6.5: 500
        ###'innodb_disable_sort_file_cache': [' boolean', ['ON', 'OFF']],
        #2
        #'innodb_large_prefix': ['boolean', ['OFF', 'ON']],
        'tmp_table_size': ['integer', [1024, 'memory_size', 1073741824]],
        #2
        #'innodb_max_dirty_pages_pct': ['numeric', [0, 99, 75]],
        #'innodb_max_dirty_pages_pct_lwm': ['numeric', [0, 99, 0]],
        'innodb_random_read_ahead': ['boolean', ['ON', 'OFF']],
        ###'max_length_for_sort_data': ['integer', [4, 10240, 1024]],
        ###'read_rnd_buffer_size': ['integer', [1, min(memory_size, 5242880), 524288]],
        'table_open_cache_instances': ['integer', [1, 64, 16]],
        'thread_cache_size': ['integer', [0, 1000, 512]],
        #1
        #'max_write_lock_count': ['integer', [1, 18446744073709551615, 18446744073709551615]],
        ###'query_alloc_block_size': ['integer', [1024, min(memory_size, 134217728), 8192]],
        ###'query_cache_limit': ['integer', [0, min(memory_size, 134217728), 1048576]],
        ###'query_cache_size': ['integer', [0, min(memory_size, int(memory_size*0.5)), 0]],
        ###'query_cache_type': ['enum', ['ON', 'DEMAND', 'OFF']],
        ###'query_prealloc_size': ['integer', [8192, min(memory_size, 134217728), 8192]],
        ###'transaction_prealloc_size': ['integer', [1024, min(memory_size, 131072), 4096]],
        #1
        #'max_seeks_for_key': ['integer', [1, 18446744073709551615, 18446744073709551615]],
        ###'sort_buffer_size': ['integer', [32768, min(memory_size, 134217728), 524288]],
        'innodb_io_capacity': ['integer', [100, 2000000, 20000]],
        'innodb_lru_scan_depth': ['integer', [100, 10240, 1024]],
        ###'innodb_old_blocks_time': ['integer', [0, 10000, 1000]],
        #1
        #'innodb_purge_batch_size': ['integer', [1, 5000, 300]],
        'innodb_spin_wait_delay': ['integer', [0, 60, 6]],
        'innodb_adaptive_hash_index_parts': ['integer', [1, 512, 8]],
        'innodb_page_cleaners': ['integer', [1, 64, 4]],
        'innodb_flush_neighbors': ['enum', [0, 2, 1]], 

        # two ## is not allowed, one # is allowed but not need
        ##'max_heap_table_size': ['integer', [16384, min(memory_size, 1844674407370954752), 16777216]],
        ##'transaction_alloc_block_size': ['integer', [1024, min(memory_size, 131072), 8192]],
        ##'range_alloc_block_size': ['integer', [4096, min(memory_size, 18446744073709551615), 4096]],
        ##'query_cache_min_res_unit': ['integer', [512, min(memory_size, 18446744073709551615), 4096]],
        ##'sql_buffer_result' : ['boolean', ['ON', 'OFF']],
        ##'max_prepared_stmt_count' : ['integer', [0, 1048576, 1000000]],
        ##'max_digest_length' : ['integer', [0, 1048576, 1024]],
        ##'max_binlog_stmt_cache_size': ['integer', [4096, min(memory_size, 18446744073709547520),
        ##                                            18446744073709547520]],
        ## 'innodb_numa_interleave' : ['boolean', ['ON', 'OFF']],
        ##'binlog_max_flush_queue_time' : ['integer', [0, 100000, 0]],
        #'innodb_commit_concurrency': ['integer', [0, 1000, 0]],
        ##'innodb_additional_mem_pool_size': ['integer', [2097152,min(memory_size,4294967295), 8388608]],
        #'innodb_thread_sleep_delay' : ['integer', [0, 1000000, 10000]],
        ##'thread_stack' : ['integer', [131072, memory_size, 524288]],
        #'back_log' : ['integer', [1, 65535, 900]],
        #BELOW: potential knob additions
        #'innodb_adaptive_max_sleep_delay': ['integer', [0, 1000000, 150000]],
        #'eq_range_index_dive_limit': ['integer', [0, 10000, 200]],
        #'innodb_change_buffer_max_size': ['integer', [0, 50, 25]],
        #'innodb_log_buffer_size': ['integer', [262144, 'memory_lower_bound', 67108864]],
        #'join_buffer_size': ['integer', [128, 'memory_lower_bound', 262144]],
        #'innodb_flushing_avg_loops': ['integer', [1, 1000, 30]],

    }
    KNOBS = {
        'table_open_cache': ['integer', [1, 10240, 512]],
        'innodb_buffer_pool_size': ['integer', [5242880, 'memory_size', 30000000*5]],
        'innodb_buffer_pool_instances': ['integer', [1, 64, 10]],
        'thread_cache_size': ['integer', [0, 1000, 512]],
        'innodb_purge_threads': ['integer', [1, 32, 3]],
        'tmp_table_size': ['integer', [1024, 'memory_size', 1073741824]],
        'innodb_read_io_threads': ['integer', [1, 64, 8]],
        'innodb_write_io_threads': ['integer', [1, 64, 8]],
        'innodb_thread_concurrency': ['integer', [0, 100, 0]],
        'innodb_sync_array_size': ['integer', [1, 1024, 1]],
        'innodb_io_capacity': ['integer', [100, 2000000, 20000]],
        'innodb_adaptive_max_sleep_delay': ['integer', [0, 1000000, 150000]],
        #'innodb_adaptive_hash_index': ['boolean', ['ON', 'OFF']],
    }
    '''
    KNOB_DEFAULTS = {
        #KNOB SETTINGS MYSQL MAC
        "table_open_cache": 4000,
        "innodb_buffer_pool_size": 134217728,
        "innodb_buffer_pool_instances": 1,
        "innodb_purge_threads": 4,
        "innodb_read_io_threads": 4,
        "innodb_write_io_threads": 4,
        "innodb_read_ahead_threshold": 56,
        "innodb_sync_array_size": 1,
        "innodb_sync_spin_loops": 30,
        "innodb_thread_concurrency": 0,
        "innodb_adaptive_hash_index": 1,
        "tmp_table_size": 16777216,
        "innodb_random_read_ahead": 0,
        "table_open_cache_instances": 16,
        "thread_cache_size": 9,
        "innodb_io_capacity": 200,
        "innodb_lru_scan_depth": 1024,
        "innodb_spin_wait_delay": 6,
        "innodb_adaptive_hash_index_parts": 8,
        "innodb_page_cleaners": 1,
        "innodb_flush_neighbors": 0,
        "innodb_adaptive_max_sleep_delay": 150000,
        #"eq_range_index_dive_limit": 200,
        #"innodb_change_buffer_max_size": 25,
        #"innodb_log_buffer_size": 16777216,
        #"join_buffer_size": 262144,
        #"innodb_flushing_avg_loops": 30,
    }
    '''
    KNOB_DEFAULTS = {
        #KNOB DEFAULTS UBUNTU
        "innodb_adaptive_max_sleep_delay": 150000,
        "innodb_buffer_pool_instances": 1,
        "innodb_buffer_pool_size": 134217728,
        "innodb_io_capacity": 200,
        "innodb_purge_threads": 4,
        "innodb_read_io_threads": 4,
        "innodb_sync_array_size": 1,
        "innodb_thread_concurrency": 0,
        "innodb_write_io_threads": 4,
        "table_open_cache": 4000,
        "thread_cache_size": 9,
        "tmp_table_size": 16777216
    }
    knob_num = len(KNOBS)

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
            allow_local_infile=True
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

    '''
    @classmethod
    @property
    def knob_num(cls) -> int:
        return len(cls.KNOBS)
    '''

    @DB_EXISTS()
    def tpcc_metrics(self, l:int = 30) -> dict:
        results = subprocess.run(['./tpcc_start', '-h', '127.0.0.1', 
                '-d', self.database, '-uroot', 
                '-p', 'Gobronxbombers2', '-w', '50', 
                '-c', '6', '-r', '0', '-l', str(l), '-i', '2'], 
            cwd = "tpcc-mysql", capture_output=True).stdout.decode('ascii')

        #print(results)
        if self.stdout_f is not None:
            self.stdout_f.write('\n'+results+'\n')
            
        tps, latency, count = 0, 0, 0
        for i in results.split('\n'):
            if (j:=re.findall('(?<=trx\:\s)\d+(?:\.\d+)*|(?<=,\s95\:\s)\d+\.\d+|(?<=,\s99\:\s)\d+\.\d+|(?<=,\smax_rt\:\s)\d+\.\d+', i)):
                _trx, _95, _99, _max_rt = map(float, j)
                tps += _trx
                latency += _99
                count += 1
        
        return {'throughput':tps/count, 'latency':latency/count}

    @DB_EXISTS()
    def sysbench_metrics(self, seconds:int = 10) -> dict:
        '''
        '--auto_inc=off',
            '--create_secondary=off',
            '--delete_inserts=5',
            '--distinct_ranges=2',
            '--index_updates=2',
            '--non_index_updates=4',
            '--order_ranges=2',
            '--point_selects=2',
            '--simple_ranges=1',
            '--sum_ranges=2',
            '--range_selects=on',
            '--secondary=off',
        '''
        assert self.database in ['sysbench_tune']
        results = str(subprocess.run(['sysbench', 'oltp_read_write',
            '--db-driver=mysql',
            '--mysql-db=sysbench_tune',
            '--mysql-user=root',
            '--mysql-password=Gobronxbombers2',
            '--mysql_storage_engine=innodb',
            '--threads=2',
            f'--time={seconds}',
            '--forced-shutdown=1',
            '--rand-seed=1',
            '--table_size=1000000',
            '--tables=10',
            '--rand-type=uniform', 
        'run'], capture_output=True).stdout.decode())
        throughput = float(re.findall('queries\:\s+\d+\s+\((\d+(?:\.\d+)*)\sper sec\.\)', results)[0])
        latency_max = float(re.findall('max\:\s+(\d+(?:\.\d+)*)', results)[0])
        latency_95th = float(re.findall('95th percentile\:\s+(\d+(?:\.\d+)*)', results)[0])
        
        return {
            'throughput': throughput,
            'latency_max': latency_max,
            'latency_95th': latency_95th
        }

    @DB_EXISTS()
    def sysbench_prepare_benchmark(self) -> None:
        assert self.database in ['sysbench_tune']
        results = str(subprocess.run(['sysbench', 'oltp_read_write',
            '--db-driver=mysql', 
            '--mysql-db=sysbench_tune', 
            '--mysql-user=root', 
            '--mysql-password=Gobronxbombers2', 
            '--mysql_storage_engine=innodb', 
            '--auto_inc=off', 
            '--create_secondary=off', 
            '--delete_inserts=5', 
            '--distinct_ranges=2', 
            '--index_updates=2', 
            '--non_index_updates=4', 
            '--order_ranges=2', 
            '--point_selects=2', 
            '--simple_ranges=1', 
            '--sum_ranges=2', 
            '--range_selects=on', 
            '--secondary=off', 
            '--table_size=1000000', 
            '--tables=10', 
            '--rand-type=uniform',
        'prepare'], capture_output=True).stdout.decode())
        print(results)

    @DB_EXISTS()
    def sysbench_cleanup_benchmark(self) -> None:
        assert self.database in ['sysbench_tune']
        results = str(subprocess.run(['sysbench', 'oltp_read_write',
            '--db-driver=mysql', 
            '--mysql-db=sysbench_tune', 
            '--mysql-user=root', 
            '--mysql-password=Gobronxbombers2', 
            '--mysql_storage_engine=innodb', 
            '--threads=50', 
            '--time=10', 
            '--forced-shutdown=1', 
            '--auto_inc=off', 
            '--create_secondary=off', 
            '--delete_inserts=5', 
            '--distinct_ranges=2', 
            '--index_updates=4', 
            '--non_index_updates=2', 
            '--order_ranges=2', 
            '--point_selects=2', 
            '--simple_ranges=1', 
            '--sum_ranges=2', 
            '--range_selects=on', 
            '--secondary=off', 
            '--table_size=1000000', 
            '--tables=10', 
            '--rand-type=uniform',
        'cleanup'], capture_output=True).stdout.decode())
        print(results)
    

    @DB_EXISTS()
    def tpcc_sysbench_metrics(self, seconds:int = 10, scale:int = 25) -> typing.List:
        assert self.database in ['sysbench_tpcc']
        results = str(subprocess.run(['./tpcc.lua', '--mysql-user=root', 
                '--mysql-password=Gobronxbombers2', '--mysql-db=sysbench_tpcc', 
                f'--time={seconds}', '--threads=8', '--report-interval=1', 
                '--tables=1', f'--scale={scale}', '--db-driver=mysql', 'run'], 
            cwd = '/opt/homebrew/Cellar/sysbench', capture_output=True).stdout)
        
        tps = [*map(float, re.findall('(?<=tps:\s)\d+(?:\.\d+)*', results))]
        qps = [*map(float, re.findall('(?<=qps:\s)\d+(?:\.\d+)*', results))]
        ltnc = re.findall('Latency \(ms\)\:[\w\W]+', results)[0]
        latency_min = float(re.findall('(?<=min:)\s+\d+(?:\.\d+)*', results)[0].lstrip())
        latency_avg = float(re.findall('(?<=avg:)\s+\d+(?:\.\d+)*', results)[0].lstrip())
        latency_max = float(re.findall('(?<=max:)\s+\d+(?:\.\d+)*', results)[0].lstrip())
        latency_95 = float(re.findall('(?<=percentile:)\s+\d+(?:\.\d+)*', results)[0].lstrip())
        latency_sum = float(re.findall('(?<=sum:)\s+\d+(?:\.\d+)*', results)[0].lstrip())
        return {
            'tps':sum(tps)/len(tps),
            'qps':sum(qps)/len(qps),
            'latency_min':latency_min,
            'latency_avg':latency_avg,
            'latency_max':latency_max,
            'latency_95':latency_95,
            'latency_sum':latency_sum
        }

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
        return {'cost':float(data['query_block']['cost_info']['query_cost']),
            'indices':[*self.__class__.used_index_lookup(data)]}

    @DB_EXISTS()
    def workload_cost(self) -> dict:
        queries = {}
        if self.database in ['tpcc100', 'tpcc_1000', 'tpcc_30']:
            for q in os.listdir('tpc/tpcc/queries'):
                with open(os.path.join('tpc/tpcc/queries', q)) as f:
                    queries[q] = self.get_query_stats(f.read())
        
            return queries

        if self.database == 'tpch1':
            with open('tpc/tpch/queries.sql') as f:
                for i, q in enumerate(f, 1):
                    queries[f'q{i}.sql'] = self.get_query_stats(q.strip(';\n'))

            return queries

        if self.database == 'sysbench_tpcc':
            for q in os.listdir('tpc/tpcc/queries_sys'):
                with open(os.path.join('tpc/tpcc/queries_sys', q)) as f:
                    queries[q] = self.get_query_stats(f.read())
        
            return queries


    @DB_EXISTS()
    def apply_index_configuration(self, indices:typing.List[int]) -> None:
        col_state = self.get_columns_from_database()
        assert len(indices) == len(col_state)
        for i, (ind_state, col_data) in enumerate(zip(indices, col_state), 1):
            if col_data['INDEX_NAME'] is not None and col_data['INDEX_NAME'].lower().startswith('PRIMARY'.lower()):
                continue

            if ind_state:
                if col_data['INDEX_NAME'] is None:
                    if col_data['DATA_TYPE'].lower() == 'text':
                        self.cur.execute(f'create index ATLAS_INDEX_{i} on {col_data["TABLE_NAME"]}({col_data["COLUMN_NAME"]}({min(20, int(col_data["CHARACTER_MAXIMUM_LENGTH"]))}))')

                    else:
                        self.cur.execute(f'create index ATLAS_INDEX_{i} on {col_data["TABLE_NAME"]}({col_data["COLUMN_NAME"]})')

            else:
                if col_data['INDEX_NAME'] is not None and not col_data['INDEX_NAME'].lower().startswith('PRIMARY'.lower()):
                    try:
                        self.cur.execute(f'drop index {col_data["INDEX_NAME"]} on {col_data["TABLE_NAME"]}')
                    except:
                        pass
        self.commit() 

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

    @classmethod
    def queries(cls) -> typing.List:
        with open('tpc/tpch/queries.sql') as f:
            return [i.strip(';\n') for i in f]

    @classmethod
    def refresh_function1(cls, sf:int, stream) -> float:
        orders = '170|510698|P|167013.41|1995-06-06|3-MEDIUM|Clerk#000001498|0|breach fluffily above the pinto|'.split('|')
        orders[0] = random.randint(1, 6006000)

        lineitem = '12|787559|7598|5|10|16465.20|0.00|0.02|A|F|1993-01-25|1993-01-07|1993-02-13|DELIVER IN PERSON|AIR|uriously ironic excuses. blithely iron|'.split('|')
        lineitem[0] = random.randint(1, 6006012)
        t = time.time()
        for _ in range(sf*1500):
            stream.execute(f'insert into orders values({", ".join("%s" for _ in orders)})', orders)
        
            for _ in range(random.randint(1, 7)):
                stream.execute(f'insert into lineitem values({", ".join("%s" for _ in lineitem)})', lineitem)

        stream.commit()
        return time.time() - t

    @classmethod
    def refresh_function2(cls, sf:int, stream) -> float:
        t = time.time()
        for _ in range(sf*1500):
            stream.execute('delete from orders where o_orderkey = %s', [random.randint(1, 6006000)])
            stream.execute('delete from lineitem where l_orderkey = %s', [random.randint(1, 6006012)])
            
        stream.commit()
        return time.time() - t

    @classmethod
    def refresh_stream(cls, sf:int) -> float:
        with cls(database = "tpch1") as rf1:
            with cls(database = "tpch1") as rf2:
                cls.refresh_function1(sf, rf1)
                cls.refresh_function2(sf, rf2)

    @classmethod
    def tpch_query_set(cls, query_ids:typing.List[int], stream) -> typing.List[float]:
        with open('tpc/tpch/queries.sql') as f:
            q_times = []
            for i, a in enumerate(f, 1):
                if i in query_ids:
                    t = time.time()
                    stream.execute(a.strip(';\n'))
                    _ = stream.cur.fetchall()
                    q_times.append(time.time() - t)
            
            return q_times

    @classmethod
    def tpch_query_stream(cls, query_ids:typing.List[int]) -> None:
        with cls(database = "tpch1") as stream:
            _ = cls.tpch_query_set(query_ids, stream)
        

    @classmethod
    def tpch_power_test(cls, sf:int, query_ids:typing.List[int]) -> float:
        with cls(database = "tpch1") as rf_stream:
            rf1_t = cls.refresh_function1(sf, rf_stream)
            with cls(database = "tpch1") as query_stream:
                q_times = cls.tpch_query_set(query_ids, query_stream)

            rf2_t = cls.refresh_function2(sf, rf_stream)

        return (3600*sf)/pow(functools.reduce(lambda x, y:x*y, q_times) * rf1_t * rf2_t, 1/(len(query_ids) + 2))

    @classmethod
    def tpch_throughput_test(cls, S:int, sf:int, query_ids:typing.List[int]) -> float:
        with concurrent.futures.ProcessPoolExecutor() as pool:
            t = time.time()
            qs1 = pool.submit(cls.tpch_query_stream, query_ids)
            qs2 = pool.submit(cls.tpch_query_stream, query_ids)
            rf = pool.submit(cls.refresh_stream, sf)

            _ = qs1.result()
            _ = qs2.result()
            _ = rf.result()
            T = time.time() - t

        return (S*len(query_ids)*3600)/T * sf


    @DB_EXISTS()
    def tpch_qphH_size(self) -> float:
        assert self.database in ['tpch1']
        #[1, 2, 3, 4, 5, 6, 7, 9, 12, 17, 18, 19]
        power = self.__class__.tpch_power_test(1, [1, 2, 3, 4, 5, 6, 7])
        throughput = self.__class__.tpch_throughput_test(2, 1, [1, 2, 3, 4, 5, 6, 7])
        return pow(power*throughput, 0.5)

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
    with MySQL(database = "sysbench_tune") as conn:
        '''
        conn.execute("create table test_stuff (id int, first_col int, second_col int, third_col int)")
        conn.execute("create index test_index on test_stuff (first_col)")
        conn.execute("create index another_index on test_stuff (second_col, third_col)")
        conn.commit()
        '''
        #print(conn.metrics(20))
        #print(len(MySQL.KNOBS))
        #print(conn.memory_size())
        #print(conn.get_knobs())
        #print(MySQL.metrics_to_list(conn._metrics()))
        #print(MySQL.metrics_to_list(conn.metrics(20)))
        #TODO: explain query cost
        #TODO: explain to check if query has utilized a specific column
        #print(MySQL.col_indices_to_list(conn.get_columns("test_stuff")))
        #print(MySQL.tpcc_metrics())
        #print(conn.memory_size('gb'))
        #print(len([(i['TABLE_NAME'], i["COLUMN_NAME"]) for i in conn.get_columns_from_database()]))
        #print(MySQL.col_indices_to_list(conn.get_columns_from_database()))
        #assert conn.db_column_count == len(conn.get_columns_from_database())
        #conn.apply_index_configuration([0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1])
        #print(conn._metrics())
        #print(conn.apply_knob_configuration({'innodb_purge_threads':5}))
        #print(json.dumps({i:conn.get_knob_value(i) for i in MySQL.KNOBS}, indent=4))
        

        #print('before', conn.get_knob_value('table_open_cache'))
        #print('before', conn.get_knob_value('innodb_random_read_ahead'))
        #conn.apply_knob_configuration({'innodb_read_ahead_threshold': 30, 'innodb_random_read_ahead':'ON'})
        #print('after', conn.get_knob_value('innodb_read_ahead_threshold'), conn.get_knob_value('thread_cache_size'))
        #conn.reset_knob_configuration()
        #print(conn.memory_size('gb'))
        #print(conn.db_column_count, len(MySQL.col_indices_to_list(conn.get_columns_from_database())))
        #print(conn.workload_cost())
        #print(conn.tpcc_metrics(2))
        '''
        t = time.time()
        print(conn.tpcc_sysbench_metrics())
        print(time.time() - t)
        #print(time.time() - t)
        '''
        #print(conn.memory_size('gb'))
        #print([(i['TABLE_NAME'], i["COLUMN_NAME"]) for i in conn.get_columns_from_database()])
        #print(conn.tpcc_metrics(2))
        #simple_refresh()
        #conn.drop_all_indices()
        #print([col_data['INDEX_NAME']for col_data in conn.get_columns_from_database()])
        '''
        t = time.time()
        print(conn.tpch_qphH_size())
        print(time.time() - t)
        '''
        #5242880
        #9005301760
        #print(conn.memory_size('b')['sysbench_tune']*4)
        #print(conn.dqn_knob_actions())
        '''
        print(conn.apply_knob_configuration({
            'innodb_buffer_pool_size': 5900000, 
            'innodb_purge_threads': 3, 
            'innodb_read_io_threads': 5, 
            'innodb_write_io_threads': 7, 
            'table_open_cache': 1000
        }))
        '''
        #print(conn.reset_knob_configuration())
        #print(conn.memory_size('gb')['sysbench_tune'])
        #d = conn._metrics()
        #print({i:d[i] for i in MySQL.VALUE_METRICS})
        #print(json.dumps(conn.get_knobs_as_dict(), indent=4))
        #print(MySQL.col_indices_to_list(conn.get_columns_from_database()))
        print(conn.metrics(5,1))
        

        