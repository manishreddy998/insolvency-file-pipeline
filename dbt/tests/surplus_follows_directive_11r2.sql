-- Para 5(6): family surplus under 200 pays nothing; 200 or more and the debtor pays half of their share.
-- Any row returned is a failure.
select file_id, family_surplus, debtor_surplus, line15_monthly_payment
from {{ ref('fct_surplus_income') }}
where (family_surplus < 200 and line15_monthly_payment <> 0)
   or (family_surplus >= 200 and abs(line15_monthly_payment - round(debtor_surplus * 0.5, 2)) > 0.01)
