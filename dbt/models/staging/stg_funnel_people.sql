select
    cluster as person_key,
    first_touch,
    last_touch,
    first_ts::timestamp as first_touch_at,
    touches::int as touches,
    consult::int = 1 as consulted,
    signed::int = 1 as signed,
    filed::int = 1 as filed,
    file_id
from {{ source('raw', 'funnel_people') }}
