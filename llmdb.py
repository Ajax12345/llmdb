import typing, collections
import sqlglot, os, re
import db_gpt, json
import sklearn.cluster
import sklearn.manifold
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

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

class Workload:
    def __init__(self, workload:str) -> None:
        self.workload = workload
        self.queries = parse_workload(workload)
        self.tables = parse_workload_schema(workload)
        self._query_embeddings = load_workload_embeddings(workload)
        self._table_embeddings = load_workload_schema_embeddings(workload)
        assert self.query_num == len(self._query_embeddings)
        assert self.table_num == len(self._table_embeddings)

    @property
    def query_embeddings(self) -> typing.List[list]:
        return [self._query_embeddings[i] for i in sorted(self.queries)]

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
                kmeans.fit(matrix:=self.query_embeddings)
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
    #vectorize_workload('tpcds')
    for i in ['tpch', 'tpcds', 'job']:
        w = Workload(i)
        w.display_query_clusters()