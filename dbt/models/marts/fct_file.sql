-- one row per intake packet read by the production extractor
with f as (select * from {{ ref('stg_packet_files') }}),
checks as (
    select file_id, count(*) filter (where severity = 'check') as checks,
           string_agg(code, ', ' order by code) filter (where severity = 'check') as check_codes
    from {{ ref('stg_packet_findings') }} group by file_id
)
select
    f.file_id,
    f.extractor,
    f.fsa,
    f.persons,
    f.debtor_monthly,
    f.spouse_monthly,
    f.unsecured_total,
    f.n_fields,
    f.n_review_fields,
    coalesce(c.checks, 0) as checks,
    c.check_codes,
    case when coalesce(c.checks, 0) = 0 and f.n_review_fields = 0 then 'ready' else 'needs review' end as status
from f left join checks c using (file_id)
