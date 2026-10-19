select
    file_id,
    month::date as month,
    m::int as month_number,
    due::numeric(12, 2) as due,
    paid::numeric(12, 2) as paid,
    days_late::int as days_late,
    nsf::int = 1 as nsf,
    partial::int = 1 as partial,
    missed::int = 1 as missed,
    arrears_payments::numeric(8, 3) as arrears_payments
from {{ source('raw', 'proposal_payments') }}
