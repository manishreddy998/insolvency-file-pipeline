select touch_id, channel, ts::timestamp as touched_at, cluster as person_key
from {{ source('raw', 'lead_touches') }}
