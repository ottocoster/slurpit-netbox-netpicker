import pynetbox
import json
from reconcile import store_reconcile

# Initialize the pynetbox API connection
nb = pynetbox.api(
    'http://localhost:8000',
    token='028d32715cbe39df0c9409649026c1e20a80bdb5'
)

# Mapping for IP ranges
mapping_ip_range = {
    "start_address": "",  # Required: The start of the IP range
    "end_address": "",    # Required: The end of the IP range
    "status": "active",   # Optional: The status of the IP range (e.g., "active")
    "role": None,         # Optional: The role of the IP range (e.g., "management")
    "tenant": None,       # Optional: The tenant to which the IP range is assigned (ID or unique identifier)
    "vrf": None,          # Optional: The VRF to which this IP range is assigned
    "site": None,         # Optional: The site to which this IP range is assigned
    "description": "",    # Optional: Free-text description
    "tags": [],           # Optional: List of tags associated with the IP range
    "custom_fields": {}   # Optional: Dictionary of custom fields defined in your NetBox instance
}


# Reconcile Flag
reconcile = True

slurpit_ip_ranges = [
    {
        "start_address": "192.168.0.1",
        "end_address": "192.168.0.100"
    },
    {
        "start_address": "10.0.0.1",
        "end_address": "10.0.0.50"
    }
]

def add_ip_ranges():
    try:
        """Adds IP ranges to NetBox."""
        create_queues = []
        for ip_range in slurpit_ip_ranges:
            create_queues.append({
                **ip_range, **mapping_ip_range
            })

        # Bulk Create
        if reconcile:
            data = []
            for item in create_queues:
                data.append(('ip_range', json.dumps(item)))
            
            if len(data):
                store_reconcile(data)

        else:
            nb.ipam.ip_ranges.create(create_queues)
    except Exception as e:
        print(f"Error adding IP ranges: {e}")

def update_ip_ranges():
    """Updates existing IP ranges in NetBox."""
    update_queues = []
    for new_ip_range in slurpit_ip_ranges:
        try:
            # Retrieve the existing IP range based on start and end address
            ip_range = nb.ipam.ip_ranges.get(start_address=new_ip_range['start_address'])
            if ip_range:
                # Prepare the update data
                update_data = {**new_ip_range, "id": ip_range.id}
                update_queues.append(update_data)
            else:
                print(f"No IP range found starting from: {new_ip_range['start_address']}")
        except Exception as e:
            print(f"Error fetching IP range {new_ip_range['start_address']}: {e}")

    # Perform the update if there are any IP ranges to update
    if update_queues:
        try:
            nb.ipam.ip_ranges.update(update_queues)
            print(f"Successfully updated IP ranges: {[ip['start_address'] for ip in update_queues]}")
        except Exception as e:
            print(f"Error updating IP ranges: {e}")

# Execute the functions
add_ip_ranges()
# update_ip_ranges()
