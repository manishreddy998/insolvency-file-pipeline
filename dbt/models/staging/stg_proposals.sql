select
    file_id,
    start::date as start_month,
    income_type,
    payment::numeric(12, 2) as monthly_payment,
    term::int as term_months,
    payment_to_income::numeric(8, 4) as payment_to_income,
    intake_flags::int as intake_flags,
    prior_insolvency::int = 1 as prior_insolvency,
    pad::int = 1 as pre_authorized_debit,
    outcome,
    end_month::date as end_month,
    paid_total::numeric(14, 2) as paid_total
from {{ source('raw', 'proposals') }}
