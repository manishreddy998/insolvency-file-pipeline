select file_id, code, severity, message, pages
from {{ source('raw', 'packet_findings') }}
