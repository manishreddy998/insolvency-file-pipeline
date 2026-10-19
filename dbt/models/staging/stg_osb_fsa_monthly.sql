select
    month::date as month,
    province,
    fsa,
    consumer_bankruptcies::int as consumer_bankruptcies,
    consumer_proposals::int as consumer_proposals,
    consumer_insolvencies::int as consumer_insolvencies,
    cp_liabilities::numeric(16, 2) as proposal_liabilities
from {{ source('raw', 'osb_fsa_monthly') }}
