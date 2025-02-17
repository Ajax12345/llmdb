import typing, collections
import sqlglot, os, re
import db_gpt, json
import sklearn.cluster
import sklearn.manifold
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np, mysql_conn
import warnings, functools
import time, torch, torch.nn
import contextlib

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

def parse_workload_schema(workload:str) -> dict:
    with open(f'{workload}_schema/schema.sql') as f:
        return {i.this.this.name:i for i in sqlglot.parse(f.read())}
    

def vectorize_workload(workload:str) -> None:
    with open(f'{workload}_schema/query_embeddings.json', 'w') as f:
        json.dump({a:db_gpt.get_embedding(db_gpt.CLIENT, b.sql()) 
            for a, b in parse_workload(workload).items()}, f)

def vectorize_schema(workload:str) -> None:
    with open(f'{workload}_schema/schema_embeddings.json', 'w') as f:
        json.dump({a:db_gpt.get_embedding(db_gpt.CLIENT, b.sql()) 
            for a, b in parse_workload_schema(workload).items()}, f)

def load_workload_embeddings(workload:str) -> dict:
    with open(f'{workload}_schema/query_embeddings.json') as f:
        return json.load(f)

def load_workload_schema_embeddings(workload:str) -> dict:
    with open(f'{workload}_schema/schema_embeddings.json') as f:
        return json.load(f)

def parse_indexes_from_gpt(response:str) -> typing.List:
    return json.loads(re.findall('(?<=```json)[^`]+(?=```)', response)[0])

def parse_tables_in_query(query:str) -> typing.Set[str]:
    try:

        return {i.this.name for i in sqlglot.parse(query)[0].find_all(sqlglot.exp.Table)}
    
    except sqlglot.errors.ParseError:
        return {i for j in re.findall('(?<=from)\s*[\w_]+(?:\s*,\s*[\w_]+)*', query.lower())
                for i in re.split('\s*,\s*', j)}


def workload_query_table_mappings(workload:str) -> None:
    with open(f'{workload}_schema/query_table_mappings.json', 'w') as f:
        json.dump({a:[*parse_tables_in_query(b.sql())] for a, b in parse_workload(workload).items()}, f)

def load_workload_query_table_mappings(workload:str) -> dict:
    with open(f'{workload}_schema/query_table_mappings.json') as f:
        return {a:set(b) for a, b in json.load(f).items()}

class Policy:
    def __init__(self, 
            table:str, 
            queries:typing.List[str], 
            probabilities:torch.tensor, 
            workload:'Workload') -> None:
        
        self.table = table
        self.queries = queries
        self.probabilities = probabilities
        self.workload = workload

    @property
    def table_columns(self) -> typing.List[str]:
        return [i.this.this for i in self.workload.tables[self.table].this.expressions]

    def action(self) -> typing.List[str]:
        '''
        Ensure that recommended columns from GPT actually exist in the table
        Remove any explicit aliasing in column recommendation i.e table.col => col
        '''
    
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.table})'


class Workload:
    def __init__(self, workload:str) -> None:
        self.workload = workload
        self.queries = parse_workload(workload)
        self.tables = parse_workload_schema(workload)
        self._query_embeddings = load_workload_embeddings(workload)
        self._table_embeddings = load_workload_schema_embeddings(workload)
        self._query_table_mappings = load_workload_query_table_mappings(workload)
        assert self.query_num == len(self._query_embeddings)
        assert self.table_num == len(self._table_embeddings)

    @property
    def query_embeddings(self) -> typing.List[list]:
        return [(i, self._query_embeddings[i]) for i in sorted(self.queries)]

    @property
    def table_num(self) -> int:
        return len(self.tables)
    
    @property
    def query_num(self) -> int:
        return len(self.queries)

    @property
    def meta(self) -> dict:
        return {
            'workload': self.workload,
            'queries': self.query_num,
            'tables': self.table_num,
        }
    
    def query_costs(self) -> dict:
        def tpch_filter(a:str) -> bool:
            return True
    
        def job_filter(a:str) -> bool:
            return not a.startswith('29')
    
        def tpcds_filter(a:str) -> bool:
            return True
        
        filters = {
            'tpch': tpch_filter,
            'job': job_filter,
            'tpcds': tpcds_filter,
        }

        with mysql_conn.MySQL(database=self.workload) as conn:
            d = {}
            for a, b in self.queries.items():
                if filters[self.workload](a):
                    try:
                        d[a] = conn.get_query_stats(b.sql())['cost']
                    except Exception as e:
                        print('got cost compute error', e)
                        print(f'skipping compute for {a}')

            return d
    
    def gen_policy_cluster(self, filters:dict, *args, **kwargs) -> typing.List[Policy]:
        k = sklearn.cluster.AgglomerativeClustering(n_clusters=self.table_num)
        q_names, embeddings = zip(*self.query_embeddings)
        k.fit(embeddings)
        d = collections.defaultdict(list)
        for a, b in zip(k.labels_, q_names):
            d[a].append(b)
        
        d_emb = {a:torch.tensor([self._query_embeddings[i] for i in b]) 
                    for a, b in d.items()}
        
        cos = torch.nn.CosineSimilarity(dim = 1)
        s_max = torch.nn.Softmax()
        print(d)
        results = []
        for a, b in self._table_embeddings.items():
            d_emb_dist = [(j, (1 - cos(k, torch.tensor([b])))) for j, k in d_emb.items()]
            cl, _emb = min(d_emb_dist, key=lambda x:x[1].min())
            print(a, d[cl], probs:=s_max(_emb*-1))
            print('-'*70)
            results.append(Policy(a, d[cl], probs, self))
        
        return results
    
    def gen_policy_top_k(self, filters:dict, k:int) -> typing.List[Policy]:
        cos = torch.nn.CosineSimilarity(dim = 0)
        s_max = torch.nn.Softmax()

        results = []
        for a, b in self._table_embeddings.items():
            emb = [(j, k, 1 - cos(torch.tensor(b), torch.tensor(k))) 
                    for j, k in self.query_embeddings \
                        if filters[self.workload](j) and {a}&self._query_table_mappings[j]]
            
            queries, _, emb_dist = zip(*sorted(emb, key=lambda x:x[-1])[:k])
            probs = s_max(torch.tensor(emb_dist)*-1)
            print(a, queries, probs)
            print('-'*5)
            results.append(Policy(a, queries, probs, self))
        
        return results

    def table_policies(self, algo:str = 'cluster', k:int = 5) -> typing.List[Policy]:
        assert algo in ['cluster', 'top_k']

        def tpch_filter(a:str) -> bool:
            return True
    
        def job_filter(a:str) -> bool:
            return not a.startswith('29') and a.endswith('a.sql')
    
        def tpcds_filter(a:str) -> bool:
            return True
        
        filters = {
            'tpch': tpch_filter,
            'job': job_filter,
            'tpcds': tpcds_filter,
        }

        return getattr(self, f'gen_policy_{algo}')(filters, k)
    
        
    def query_costs_norm(self) -> float:
        d = self.query_costs()
        print(d)
        m, m1 = min(d.values()), max(d.values())
        return sum((i-m)/(m1 - m) for i in d.values())
        #return pow(functools.reduce(lambda x, y: x*y, d.values()), 1/len(d))

    def workload_latency(self) -> float:
        with mysql_conn.MySQL(database=self.workload) as conn:
            t = time.time()
            for a, b in self.queries.items():
                print(a)
                conn.execute(b.sql())
                _ = conn.cur.fetchone()
                #conn.cur.reset()
            
            return time.time() - t

    def __repr__(self) -> str:
        return f'<{str(self.meta)}>'
    
    
    def display_query_clusters(self) -> None:
        v = [
            ('kmeans', sklearn.cluster.KMeans(n_clusters=self.table_num, init="k-means++", random_state=42)),
            ('AggCluster(cosine,complete)', sklearn.cluster.AgglomerativeClustering(n_clusters=self.table_num, metric='cosine', linkage = 'complete')),
            ('AggCluster(cosine,single)', sklearn.cluster.AgglomerativeClustering(n_clusters=self.table_num, metric='cosine', linkage = 'single')),
            ('AggCluster', sklearn.cluster.AgglomerativeClustering(n_clusters=self.table_num)),
        ]
        
        #kmeans = 
        
        fig, plts = plt.subplots(nrows=2, ncols=2)
        for p in plts:
            for P in p:
                t, kmeans = v.pop(0)
                q_names, matrix = zip(*self.query_embeddings) 
                kmeans.fit(matrix)
                print(kmeans.labels_)
                d = collections.defaultdict(list)
                for i, a in enumerate(kmeans.labels_):
                    d[a].append(i)

                tsne = sklearn.manifold.TSNE(n_components=2, perplexity=15, random_state=42, init="random", learning_rate=200)
                vis_dims2 = tsne.fit_transform(np.array(matrix))

                x = [x for x, y in vis_dims2]
                y = [y for x, y in vis_dims2]

                COLORS = ['brown', 'red', 'cadetblue', 'greenyellow', 'moccasin', 'slateblue', 'blueviolet', 'gray', 'navy', 'yellow', 'deepskyblue', 'teal', 'forestgreen', 'orange', 'violet', 'sienna', 'turquoise', 'black', 'darkkhaki', 'purple', 'orchid', 'rosybrown', 'olive', 'silver', 'maroon']
                for i, color in enumerate(COLORS[:self.table_num]):
                    xs = [x[j] for j in d[i]]
                    ys = [y[j] for j in d[i]]
                    P.scatter(xs, ys, color=color, alpha=0.3)
                
                P.set_title(t)

        plt.suptitle(f'Workload: {self.workload.upper()}')
        plt.show()


if __name__ == '__main__':
    w = Workload('tpch')
    p = w.table_policies(algo='top_k')


    with open('prompts/actor/system.txt') as f, \
            open('prompts/actor/user.txt') as f1, \
            open('prompts/actor/critic_response.txt') as f2:
        
        sys, user = f.read(), f1.read()
        query = '''\nSELECT Substr(w_warehouse_name, 1, 20), \n               sm_type, \n               web_name, \n               Sum(CASE \n                     WHEN ( ws_ship_date_sk - ws_sold_date_sk <= 30 ) THEN 1 \n                     ELSE 0 \n                   END) AS `30 days`, \n               Sum(CASE \n                     WHEN ( ws_ship_date_sk - ws_sold_date_sk > 30 ) \n                          AND ( ws_ship_date_sk - ws_sold_date_sk <= 60 ) THEN 1 \n                     ELSE 0 \n                   END) AS `31-60 days`, \n               Sum(CASE \n                     WHEN ( ws_ship_date_sk - ws_sold_date_sk > 60 ) \n                          AND ( ws_ship_date_sk - ws_sold_date_sk <= 90 ) THEN 1 \n                     ELSE 0 \n                   END) AS `61-90 days`, \n               Sum(CASE \n                     WHEN ( ws_ship_date_sk - ws_sold_date_sk > 90 ) \n                          AND ( ws_ship_date_sk - ws_sold_date_sk <= 120 ) THEN \n                     1 \n                     ELSE 0 \n                   END) AS `91-120 days`, \n               Sum(CASE \n                     WHEN ( ws_ship_date_sk - ws_sold_date_sk > 120 ) THEN 1 \n                     ELSE 0 \n                   END) AS `>120 days` \nFROM   web_sales, \n       warehouse, \n       ship_mode, \n       web_site, \n       date_dim \nWHERE  d_month_seq BETWEEN 1222 AND 1222 + 11 \n       AND ws_ship_date_sk = d_date_sk \n       AND ws_warehouse_sk = w_warehouse_sk \n       AND ws_ship_mode_sk = sm_ship_mode_sk \n       AND ws_web_site_sk = web_site_sk \nGROUP  BY Substr(w_warehouse_name, 1, 20), \n          sm_type, \n          web_name \nORDER  BY Substr(w_warehouse_name, 1, 20), \n          sm_type, \n          web_name\nLIMIT 100; \n'''
        schema = """
CREATE TABLE catalog_sales (
    cs_sold_date_sk bigint(11),
    cs_sold_time_sk bigint(11),
    cs_ship_date_sk bigint(11),
    cs_bill_customer_sk bigint(11),
    cs_bill_cdemo_sk bigint(11),
    cs_bill_hdemo_sk bigint(11),
    cs_bill_addr_sk bigint(11),
    cs_ship_customer_sk bigint(11),
    cs_ship_cdemo_sk bigint(11),
    cs_ship_hdemo_sk bigint(11),
    cs_ship_addr_sk bigint(11),
    cs_call_center_sk bigint(11),
    cs_catalog_page_sk bigint(11),
    cs_ship_mode_sk bigint(11),
    cs_warehouse_sk bigint(11),
    cs_item_sk bigint(11),
    cs_promo_sk bigint(11),
    cs_order_number bigint(11),
    cs_quantity bigint(11),
    cs_wholesale_cost decimal(7,2),
    cs_list_price decimal(7,2),
    cs_sales_price decimal(7,2),
    cs_ext_discount_amt decimal(7,2),
    cs_ext_sales_price decimal(7,2),
    cs_ext_wholesale_cost decimal(7,2),
    cs_ext_list_price decimal(7,2),
    cs_ext_tax decimal(7,2),
    cs_coupon_amt decimal(7,2),
    cs_ext_ship_cost decimal(7,2),
    cs_net_paid decimal(7,2),
    cs_net_paid_inc_tax decimal(7,2),
    cs_net_paid_inc_ship decimal(7,2),
    cs_net_paid_inc_ship_tax decimal(7,2),
    cs_net_profit decimal(7,2)
)
"""
        user = user.format(query = query, 
            schema = schema,
            table_name = "catalog_sales",
            critic_response = "")
        
        '''
        resp = db_gpt.query_gpt(db_gpt.CLIENT, sys, user)
        
        print(resp)
        print('-'*60)
        print(parse_indexes_from_gpt(resp))
        '''
    
