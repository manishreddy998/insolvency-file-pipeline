-- people (not touches) by first touch channel, followed to a filed and completed proposal
with people as (
    select fp.*, pr.outcome
    from {{ ref('stg_funnel_people') }} fp
    left join {{ ref('stg_proposals') }} pr using (file_id)
),
touches as (
    select channel, count(*) as touches from {{ ref('stg_lead_touches') }} group by channel
),
cost as (select channel, cost_per_touch::numeric(10, 2) as cost_per_touch from {{ source('raw', 'channel_cost') }})
select
    t.channel,
    t.touches,
    round(t.touches * c.cost_per_touch, 0) as spend,
    count(p.person_key) as people,
    count(*) filter (where p.consulted) as consults,
    count(*) filter (where p.filed) as filed,
    count(*) filter (where p.outcome = 'completed') as completed,
    count(*) filter (where p.outcome = 'annulled') as annulled,
    round(t.touches * c.cost_per_touch / nullif(count(*) filter (where p.filed), 0), 2) as cost_per_filed,
    round(t.touches * c.cost_per_touch / nullif(count(*) filter (where p.outcome = 'completed'), 0), 2) as cost_per_completed
from touches t
join cost c using (channel)
left join people p on p.first_touch = t.channel
group by t.channel, t.touches, c.cost_per_touch
