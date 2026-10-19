select
    file_id,
    month::date as month,
    risk::numeric(8, 5) as risk,
    arrears_payments::numeric(8, 3) as arrears_payments,
    payments_before_annulment::numeric(8, 2) as payments_before_annulment,
    annulment_if_no_payment::date as annulment_if_no_payment,
    coalesce(reasons, '') as reasons
from {{ source('raw', 'radar_scores') }}
