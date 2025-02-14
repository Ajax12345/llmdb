import typing, collections
import sqlglot, os, re

def parse_schema(workload:str) -> typing.List:
    with open(os.path.join(f'{workload}_schema', 'schema.sql')) as f:
        tbl_schema = f.read()

    return sqlglot.parse(tbl_schema)
    
def parse_workload(workload:str) -> typing.List:
    def tpch() -> dict:
        with open('tpch_schema/queries.sql') as f:
            return {f'q{i}.sql': sqlglot.parse(a)[0] 
                        for i, a in enumerate(f, 1) if a}

    def tpcds() -> dict:
        d = {}
        p = 'tpcds_schema/queries'

        class ErrWrapper:
            def __init__(self, sql:str) -> None:
                self._sql = sql
            
            def sql(self) -> str:
                return self._sql
            
    
        for i in os.listdir(p):
            if re.findall('\.sql$', i):
                with open(os.path.join(p, i)) as f:
                    try:
                        d[i] = sqlglot.parse(src:=f.read())[0]
                    except sqlglot.errors.ParseError:
                        d[i] = ErrWrapper(src)
        return d

    def job() -> dict:
        d = {}
        for i in os.listdir('job_schema'):
            if re.findall('^\d+\w\.sql', i):
                with open(os.path.join('job_schema', i)) as f:
                    d[i] = sqlglot.parse(f.read())[0]

        return d

    return {
        'tpch': tpch,
        'tpcds': tpcds,
        'job': job,

    }[workload]()

if __name__ == '__main__':
    l = parse_workload('tpcds')
    print(l['query1.sql'].sql())