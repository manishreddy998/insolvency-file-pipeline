select
    o.fsa,
    o.province,
    (select count(*) from {{ source('raw', 'office_fsas') }} r where r.fsa = o.fsa) as offices
from {{ ref('stg_office_fsas') }} o
