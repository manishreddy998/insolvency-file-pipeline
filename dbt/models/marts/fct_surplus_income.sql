-- Form 65 lines as computed under Directive 11R2-2026
select
    file_id,
    persons,
    line1_debtor_net_income,
    line2_other_members_net_income,
    line3_family_net_income,
    line6_family_non_discretionary,
    line8_family_available,
    line9_debtor_share_pct,
    standard,
    family_surplus,
    debtor_surplus,
    payable,
    line15_monthly_payment
from {{ ref('stg_packet_files') }}
where line1_debtor_net_income is not null
