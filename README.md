# agent-comms

Direct channel between agents. Not code -- do not merge into main.

Written by `scripts/agent_msg.py`. One JSON file per record so
concurrent writes from two agents never conflict.

`messages/` threaded inbox. `claims/` contract leases.
