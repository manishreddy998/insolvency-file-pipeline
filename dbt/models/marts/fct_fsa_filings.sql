-- real OSB counts by FSA and month, with the office flag and the next six month forecast
with hist as (
    select month, province, fsa, consumer_insolvencies, consumer_proposals, proposal_liabilities, false as is_forecast
    from {{ ref('stg_osb_fsa_monthly') }}
    where fsa <> '???'
),
fc as (
    select f.month::date as month, h.province, f.fsa, round(f.forecast::numeric, 1) as consumer_insolvencies,
           null::numeric as consumer_proposals, null::numeric as proposal_liabilities, true as is_forecast
    from {{ source('raw', 'osb_fsa_forecast') }} f
    join (select distinct on (fsa) fsa, province from hist order by fsa, month desc) h using (fsa)
)
select u.*, d.fsa is not null as has_office
from (select * from hist union all select * from fc) u
left join {{ ref('dim_office_fsa') }} d using (fsa)
