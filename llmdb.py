import typing, collections
import sqlglot, os

def parse_schema(workload:str) -> typing.Any:
    with open(os.path.join(f'{workload}_schema', 'schema.sql')) as f:
        tbl_schema = f.read()

    tbls = sqlglot.parse(tbl_schema)
    print(tbls[0].sql())


if __name__ == '__main__':
    parse_schema('job')