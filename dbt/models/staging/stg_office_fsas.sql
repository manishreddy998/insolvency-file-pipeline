select distinct fsa, province from {{ source('raw', 'office_fsas') }}
