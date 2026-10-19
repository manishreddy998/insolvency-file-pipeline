select
    r.*,
    rank() over (order by r.risk desc) as call_rank,
    r.arrears_payments >= 1 as on_overdue_list,
    pr.monthly_payment,
    pr.term_months
from {{ ref('stg_radar_scores') }} r
join {{ ref('stg_proposals') }} pr using (file_id)
