-- a person is counted once in the funnel
select person_key from {{ ref('stg_funnel_people') }} group by person_key having count(*) > 1
