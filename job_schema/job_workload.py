import typing, collections
import time, csv, os
import sys, re
sys.path.append("..")
import mysql_conn, typing

'''
pip3 install imdbpy
imdbpy2sql.py -d /Users/jamespetullo/Downloads/imdb -u mysql://root:Gobronxbombers2@localhost/job
'''
def get_type(val:str) -> typing.Union[str, float, int]:
    if not val:
        return
    
    if val.isdigit():
        return int(val)
    
    if re.findall('^\d+\.\d+$', val):
        return float(val)

    return val

def movie_companies(row):
    if len(row) == 5:
        return row

    return row[:4]+[' '.join(row[4:])]

def aka_name(row):
    if len(row) == 8:
        return row

    return row[:2]+[' '.join(row[2:-5])]+row[-5:]

def movie_info(row):
    if len(row) == 5:
        return row
    
    return row[:3]+[' '.join(row[3:-1]), row[-1]]

handlers = {
    'movie_companies': movie_companies,
    'aka_name': aka_name,
    'movie_info': movie_info,
}

def load_data(path = '/Users/jamespetullo/Downloads/imdb') -> None:
    for i in os.listdir(path):
        if i.endswith('.csv'):
            print(f'''
LOAD DATA LOCAL INFILE  
'{os.path.join(path, i)}'
INTO TABLE {i.replace('.csv', '')}  
FIELDS TERMINATED BY ',' 
ENCLOSED BY '"'
LINES TERMINATED BY '\\n';
            ''')
            continue
            tbl_name = i.replace('.csv', '')
            if tbl_name in ['name', 
                            'movie_companies', 
                            'aka_name',
                            'movie_info',
                            'movie_keyword', 'person_info', 
                            'comp_cast_type', 
                            'complete_cast', 
                            'char_name', 
                            'movie_link', 
                            'company_type', 
                            'cast_info', 
                            'info_type', 
                            'company_name', 
                            'aka_title', 
                            'kind_type', 'role_type', 'movie_info_idx', 'keyword', 'link_type', 'title']:
                continue
            
            with mysql_conn.MySQL(database = 'job') as conn, \
                open(os.path.join(path, i)) as f:
                conn.execute(f'delete from {tbl_name}')
                conn.commit()
                for i in csv.reader(f):
                    try:
                        bindings = handlers.get(tbl_name, lambda x:x)([*map(get_type, i)])
                        conn.execute(f'insert into {tbl_name} values ({", ".join("%s" for _ in bindings)})', bindings)
                    
                    except Exception as e:
                        print(e)
                        print(i)
                        return
                    
                conn.commit()

def exec_workload(key:str = 'a') -> float:
    dt = 0
    with mysql_conn.MySQL(database = 'job') as conn:
        for i in os.listdir('job_schema'):
            #print(i)
            if re.findall('^\d+[abc].sql', i) and i.endswith(f'{key}.sql'):
                with open(os.path.join('job_schema', i)) as f:
                    t1 = time.time()
                    conn.execute(f.read())
                    _ = conn.cur.fetchone()
                    dt += time.time() - t1
                    conn.cur.reset()
    
    return dt

if __name__ == '__main__':
    print('results here', exec_workload())
