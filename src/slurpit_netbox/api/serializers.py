from core.choices import DataSourceStatusChoices
from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from netbox.api.serializers import WritableNestedSerializer

from slurpit_netbox.models import SlurpitPlanning, SlurpitImportedDevice, SlurpitStagedDevice, SlurpitSetting, SlurpitSnapshot, SlurpitMapping, SlurpitInitIPAddress, SlurpitInterface, SlurpitPrefix, SlurpitVLAN

__all__ = (
    'SlurpitPlanningSerializer',
    'SlurpitStagedDeviceSerializer',
    'SlurpitImportedDeviceSerializer',
    'SlurpitSettingSerializer',
    'SlurpitSnapshotSerializer',
    'SlurpitInitIPAddressSerializer',
    'SlurpitInterfaceSerializer',
    'SlurpitPrefixSerializer'
)

class SlurpitPlanningSerializer(NetBoxModelSerializer):
    id = serializers.IntegerField(source='planning_id')
    comment = serializers.CharField(source='comments')

    class Meta:
        model = SlurpitPlanning
        fields = ['id', "name", "comment", "display"]

class SlurpitStagedDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlurpitStagedDevice
        fields = ['id', 'disabled', 'hostname', 'fqdn', 'ipv4', 'device_os', 'device_type', 'brand', 'createddate', 'changeddate']

class SlurpitInitIPAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlurpitInitIPAddress
        
        fields = [
            'id', 'address', 'vrf', 'tenant', 'status', 'role',
            'dns_name', 'description', 'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        ]

class SlurpitInterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlurpitInterface
        fields = [
            'id', 'device', 'module', 'name', 'label', 'type', 'enabled',
            'parent', 'bridge', 'mtu', 'mac_address', 'speed', 'duplex', 'description',
            'mode', 'tags', 'custom_fields', 'created',
            'last_updated'
        ]

class SlurpitSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlurpitSnapshot
        fields =  [ 'id', 'hostname', 'planning_id', 'content', 'result_type']


class SlurpitImportedDeviceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='slurpit_id')
    class Meta:
        model = SlurpitImportedDevice
        fields = ['id', 'disabled', 'hostname', 'fqdn', 'ipv4', 'device_os', 'device_type', 'brand', 'createddate', 'changeddate']


class SlurpitSettingSerializer(WritableNestedSerializer):
    class Meta:
        model = SlurpitSetting
        fields = [ 'id', 'server_url', 'api_key', 'last_synced', 'connection_status', 'push_api_key', 'appliance_type']

class SlurpitMappingSerializer(NetBoxModelSerializer):
    class Meta:
        model = SlurpitMapping
        fields = [ 'id', 'source_field', 'target_field']

class SlurpitVLANSerializer(NetBoxModelSerializer):
    class Meta:
        model = SlurpitVLAN
        fields = [
            'id', 'site', 'group', 'vid', 'name', 'tenant', 'status', 'role',
            'description', 'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        ]

class SlurpitPrefixSerializer(NetBoxModelSerializer):
    class Meta:
        model = SlurpitPrefix
        fields = [
            'id', 'family', 'prefix', 'vrf', 'tenant', 'vlan', 'status',
            'role', 'is_pool', 'mark_utilized', 'description', 'comments', 'tags', 'custom_fields',
            'created', 'last_updated', 'children', '_depth',
        ]