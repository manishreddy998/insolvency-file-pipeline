select
    p.file_id,
    p.month,
    p.month_number,
    p.due,
    p.paid,
    p.days_late,
    p.nsf,
    p.partial,
    p.missed,
    p.arrears_payments,
    p.arrears_payments >= 3 as at_deemed_annulment,
    pr.outcome
from {{ ref('stg_proposal_payments') }} p
join {{ ref('stg_proposals') }} pr using (file_id)
