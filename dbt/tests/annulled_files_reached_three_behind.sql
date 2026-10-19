-- BIA 66.31(1)(a): an annulled proposal must have been three payments behind at some point
select file_id
from {{ ref('fct_proposal_payment') }}
where outcome = 'annulled'
group by file_id
having max(arrears_payments) < 2.999
