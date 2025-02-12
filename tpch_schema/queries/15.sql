select
	s_suppkey,
	s_name,
	s_address,
	s_phone,
	total_revenue
from
	supplier,
	(select
		l_suppkey supplier_no,
		sum(l_extendedprice * (1 - l_discount)) total_revenue
	from
		lineitem
	where
		l_shipdate >= date '1996-12-01'
		and l_shipdate < date '1996-12-01' + interval '3' month
	group by
		l_suppkey) revenue_s
where
	s_suppkey = revenue_s.supplier_no
	and revenue_s.total_revenue = (
		select
			max(total_revenue)
		from
			(select
				l_suppkey supplier_no,
				sum(l_extendedprice * (1 - l_discount)) total_revenue
			from
				lineitem
			where
				l_shipdate >= date '1996-12-01'
				and l_shipdate < date '1996-12-01' + interval '3' month
			group by
				l_suppkey) revenue_s
			)
order by
	s_suppkey;
