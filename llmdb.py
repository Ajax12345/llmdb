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
import contextlib, random
import datetime

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


def gen_tuning_run_folder() -> str:
    d = datetime.datetime.now()
    path = f'tuning/run_{d.year}-{d.month}-{d.day}_{d.hour}_{d.minute}'
    os.mkdir(path)
    return path

class B1_Bandit:
    def __init__(self, arms:int, 
                 cold_start:int = 0, 
                 probs:typing.List[float] = None) -> None:
        
        self.arms, self.probs = arms, probs
        self.cold_start = cold_start
        self.slots = {i:[] for i in range(arms)}
        self.rounds = 0

    def update(self, arm:int, reward:float) -> None:
        self.slots[arm].append(reward)
        self.rounds += 1
    
    def get_arm(self) -> int:
        if self.rounds < self.cold_start:
            w = self.probs

        else:
            s_max = torch.nn.Softmax()
            w = s_max(torch.tensor([sum(self.slots[i])/self.rounds for i in range(self.arms)])).numpy().tolist()
        
        print(w)
        return random.choices([*range(self.arms)], w, k=1)[0]
    
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(arms={self.arms}, cold_start={self.cold_start})'

class Policy:
    def __init__(self, 
            table:str, 
            queries:typing.List[str], 
            probabilities:torch.tensor, 
            workload:'Workload',
            config:dict) -> None:
        
        self.table = table
        self.queries = queries
        self.probabilities = probabilities
        self.workload = workload
        self.config = config
        self.bandit = B1_Bandit(len(self.queries), 
            cold_start=self.config['cold_start'],
            probs = self.probabilities)

        self.table_columns = self.get_table_columns()
        self.chosen_indexes = []


    def get_table_columns(self) -> typing.List[str]:
        return [i.this.this for i in self.workload.tables[self.table].this.expressions]

    def action(self) -> typing.List[str]:
        with open('prompts/actor/system.txt') as f, \
            open('prompts/actor/user.txt') as f1, \
            open('prompts/actor/critic_response.txt') as f2:
        
            sys, user = f.read(), f1.read()
        
        chosen_arm = self.bandit.get_arm()
        query = self.queries[chosen_arm]

        user_prompt = user.format(
            query = self.workload.queries[query].sql(), 
            schema = self.workload.tables[self.table].sql(),
            table_name = self.table,
            critic_response = ""
        )
        
        print(f'user prompt here for table: {self.table}')
        print(user_prompt)
        resp = db_gpt.query_gpt(db_gpt.CLIENT, sys, user_prompt)
        print('-'*60)
        print(resp)
        _ind = parse_indexes_from_gpt(resp)
        _indexes = [j for i in _ind if (j:=re.sub('^\w+\.', '', i)) in self.table_columns]

        if not _indexes:
            reward = -2
        
        elif not self.chosen_indexes:
            reward = 1
        
        elif len(self.chosen_indexes[-1]) == len(_indexes):
            reward = 0.5
        
        else:
            reward = len(_indexes) - len(self.chosen_indexes[-1])
        
        print('reward', reward)
        print('+'*60)
        self.bandit.update(chosen_arm, reward)
        self.chosen_indexes.append(_indexes)
        return _indexes

    def to_dict(self) -> dict:
        return {
            'table': self.table,
            'indexes': self.chosen_indexes
        }

    
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
        with open('tuning/config.json') as f:
            tuning_config = json.load(f)

        results = []
        for a, b in self._table_embeddings.items():
            emb = [(j, k, 1 - cos(torch.tensor(b), torch.tensor(k))) 
                    for j, k in self.query_embeddings \
                        if filters[self.workload](j) and {a}&self._query_table_mappings[j]]
            
            queries, _, emb_dist = zip(*sorted(emb, key=lambda x:x[-1])[:k])
            probs = s_max(torch.tensor(emb_dist)*-1)
            print(a, queries, probs)
            print('-'*5)
            results.append(Policy(a, queries, probs, self, tuning_config['policy']))
        
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

def test_prompts() -> None:
    with open('prompts/actor/system.txt') as f, \
            open('prompts/actor/user.txt') as f1, \
            open('prompts/actor/critic_response.txt') as f2:
        
        sys, user = f.read(), f1.read()
        query = '''SELECT l_returnflag, l_linestatus, SUM(l_quantity) AS sum_qty, SUM(l_extendedprice) AS sum_base_price, SUM(l_extendedprice * (1 - l_discount)) AS sum_disc_price, SUM(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge, AVG(l_quantity) AS avg_qty, AVG(l_extendedprice) AS avg_price, AVG(l_discount) AS avg_disc, COUNT(*) AS count_order FROM lineitem WHERE l_shipdate <= CAST('1994-7-17' AS DATE) - INTERVAL '108' day GROUP BY l_returnflag, l_linestatus ORDER BY l_returnflag, l_linestatus'''
        schema = """
CREATE TABLE lineitem
(
    l_orderkey    BIGINT not null,
    l_partkey     BIGINT not null,
    l_suppkey     BIGINT not null,
    l_linenumber  BIGINT not null,
    l_quantity    DOUBLE PRECISION not null,
    l_extendedprice  DOUBLE PRECISION not null,
    l_discount    DOUBLE PRECISION not null,
    l_tax         DOUBLE PRECISION not null,
    l_returnflag  CHAR(1) not null,
    l_linestatus  CHAR(1) not null,
    l_shipdate    DATE not null,
    l_commitdate  DATE not null,
    l_receiptdate DATE not null,
    l_shipinstruct CHAR(25) not null,
    l_shipmode     CHAR(10) not null,
    l_comment      VARCHAR(44) not null
)
)
"""
        user = user.format(query = query, 
            schema = schema,
            table_name = "lineitem",
            critic_response = "")
        
        '''
        resp = db_gpt.query_gpt(db_gpt.CLIENT, sys, user)
        
        print(resp)
        print('-'*60)
        print(parse_indexes_from_gpt(resp))
        '''
        bandit = B1_Bandit(5, cold_start = 2, probs = [0.2114, 0.1976, 0.1973, 0.1970, 0.1967])
        for i in [1, 1, -1, 1]:
            a = bandit.get_arm()
            print(f'arm: {a}, reward: {i}')
            bandit.update(a, i)

if __name__ == '__main__':
    w = Workload('tpch')
    p = w.table_policies(algo='top_k')
    for _ in range(3):
        for i in p:
            i.action()

    
    path = gen_tuning_run_folder()
    with open(os.path.join(path, 'indexes.json'), 'w') as f:
        json.dump([i.to_dict() for i in p], f)
    
    
    
