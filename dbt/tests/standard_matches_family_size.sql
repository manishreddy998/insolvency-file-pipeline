-- 2026 standards from Directive 11R2-2026
select s.file_id, s.persons, s.standard
from {{ ref('fct_surplus_income') }} s
join (values (1, 2716), (2, 3381), (3, 4157), (4, 5047), (5, 5724), (6, 6456), (7, 7188)) v(persons, standard)
  on least(s.persons, 7) = v.persons
where s.standard not in (v.standard, round(v.standard / 2.0, 2))
