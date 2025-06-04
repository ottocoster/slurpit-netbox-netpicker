import json
import traceback
from datetime import timedelta

from rest_framework.routers import APIRootView
from rest_framework_bulk import BulkCreateModelMixin, BulkDestroyModelMixin
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status, mixins

from django.db import transaction
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType
from django.forms.models import model_to_dict
from django.utils import timezone
from django.db.models import Q, Count
from django.core.serializers import serialize

from .serializers import (
    SlurpitPlanningSerializer, 
    SlurpitSnapshotSerializer, 
    SlurpitImportedDeviceSerializer, 
    SlurpitPrefixSerializer, 
    SlurpitInterfaceSerializer, 
    SlurpitInitIPAddressSerializer,
    SlurpitVLANSerializer
)
from ..validator import (
    device_validator, 
    ipam_validator, 
    interface_validator, 
    prefix_validator,
    vlan_validator
)
from ..importer import process_import, import_devices, import_plannings, start_device_import, create_sites, sync_sites, BATCH_SIZE
from ..management.choices import *
from ..views.datamapping import get_device_dict
from ..references import base_name 
from ..references.generic import status_offline, SlurpitViewSet, status_decommissioning
from ..references.imports import * 
from ..models import (
    SlurpitPlanning, 
    SlurpitSnapshot, 
    SlurpitImportedDevice, 
    SlurpitStagedDevice,
    SlurpitMapping, 
    SlurpitInitIPAddress, 
    SlurpitInterface, 
    SlurpitPrefix,
    SlurpitVLAN
)
from ..filtersets import SlurpitPlanningFilterSet, SlurpitSnapshotFilterSet, SlurpitImportedDeviceFilterSet
from ..views.setting import sync_snapshot
from ipam.models import (
    FHRPGroup, VRF, IPAddress, VLAN, Role, Prefix, VLANGroup
)
from ipam.api.serializers import PrefixSerializer
from dcim.models import Interface, Site
from dcim.forms import InterfaceForm
from ipam.forms import (
    IPAddressForm, PrefixForm, VLANForm
)
from tenancy.models import Tenant
from django.core.cache import cache
from dcim.api.serializers_.sites import SiteSerializer

__all__ = (
    'SlurpitPlanningViewSet',
    'SlurpitRootView',
    'SlurpitDeviceView'
)

class SlurpitRootView(APIRootView):
    """
    Slurpit API root view
    """
    def get_view_name(self):
        return 'Slurpit'
    

class DeviceViewSet(
        SlurpitViewSet,
        BulkCreateModelMixin,
        BulkDestroyModelMixin,
    ):
    queryset = SlurpitImportedDevice.objects.all()
    serializer_class = SlurpitImportedDeviceSerializer
    filterset_class = SlurpitImportedDeviceFilterSet

    @action(detail=False, methods=['delete'], url_path='delete-all')
    def delete_all(self, request, *args, **kwargs):
        with transaction.atomic():
            Device.objects.select_related('slurpitimporteddevice').update(status=status_decommissioning())
            SlurpitStagedDevice.objects.all().delete()
            SlurpitImportedDevice.objects.filter(mapped_device__isnull=True).delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=['delete'], url_path='delete/(?P<hostname>[^/.]+)')
    def delete(self, request, *args, **kwargs):
        hostname_to_delete = kwargs.get('hostname')
        with transaction.atomic():
            to_delete = SlurpitImportedDevice.objects.filter(hostname=hostname_to_delete)
            Device.objects.filter(slurpitimporteddevice__in=to_delete).update(status=status_decommissioning())
            to_delete.filter(mapped_device__isnull=True).delete()
            SlurpitStagedDevice.objects.filter(hostname=hostname_to_delete).delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def create(self, request):
        sync_sites()
        errors = device_validator(request.data)
        if errors:
            return JsonResponse({'status': 'error', 'errors': errors}, status=400)
        if len(request.data) != 1:
            return JsonResponse({'status': 'error', 'errors': ['List size should be 1']}, status=400)

        start_device_import()
        import_devices(request.data)
        process_import(delete=False)
        
        return JsonResponse({'status': 'success'})
    
    @action(detail=False, methods=['post'],  url_path='sync')
    def sync(self, request):            
        errors = device_validator(request.data)
        if errors:
            return JsonResponse({'status': 'error', 'errors': errors}, status=status.HTTP_400_BAD_REQUEST)
        
        ids = [obj['id'] for obj in request.data]
        hostnames = [obj['hostname'] for obj in request.data]
        SlurpitStagedDevice.objects.filter(Q(hostname__in=hostnames) | Q(slurpit_id__in=ids)).delete()
        import_devices(request.data)        
        return JsonResponse({'status': 'success'})

    @action(detail=False, methods=['post'],  url_path='sync_start')
    def sync_start(self, request):
        sync_sites()
        threshold = timezone.now() - timedelta(days=1)
        SlurpitStagedDevice.objects.filter(createddate__lt=threshold).delete()
        return JsonResponse({'status': 'success'})

    @action(detail=False, methods=['post'],  url_path='sync_end')
    def sync_end(self, request):
        process_import()
        return JsonResponse({'status': 'success'})
    
class SlurpitTestAPIView(SlurpitViewSet):
    queryset = SlurpitImportedDevice.objects.all()
    serializer_class = SlurpitImportedDeviceSerializer
    filterset_class = SlurpitImportedDeviceFilterSet

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='api')
    def api(self, request, *args, **kwargs):    
        return JsonResponse({'status': 'success'})
    
class SlurpitDeviceView(SlurpitViewSet):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    filterset_class = DeviceFilterSet


    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request, *args, **kwargs):
        request_body = []

        devices_array = [get_device_dict(device) for device in Device.objects.all()]

        objs = SlurpitMapping.objects.all()
        
        for device in devices_array:
            row = {}
            for obj in objs:
                target_field = obj.target_field.split('|')[1]
                row[obj.source_field] = str(device[target_field])
            request_body.append(row)


        return JsonResponse({'data': request_body})
    

class SlurpitInterfaceView(SlurpitViewSet):
    queryset = SlurpitInterface.objects.all()

    def get_serializer_class(self):
        return SlurpitInterfaceSerializer
    
    def create(self, request):
        # Validate request Interface data
        errors = interface_validator(request.data)
        if errors:
            return JsonResponse({'status': 'error', 'errors': errors}, status=400)

        try:
            # Get initial values for Interface
            enable_reconcile = True
            initial_obj = SlurpitInterface.objects.filter(name='').values(
                'module', 'type', 'speed', 'label', 'description', 'duplex', 'enable_reconcile', 'ignore_module', 'ignore_type', 'ignore_speed', 'ignore_duplex', 'enabled'
            ).first()
            initial_interface_values = {}
            interface_update_ignore_values = []

            if initial_obj:
                enable_reconcile = initial_obj['enable_reconcile']
                del initial_obj['enable_reconcile']
                initial_interface_values = {**initial_obj}

                for key in initial_interface_values.keys():
                    if key.startswith('ignore_') and initial_interface_values[key]:
                        interface_update_ignore_values.append(key)
            else:
                initial_interface_values = {
                    'type': "other",
                    'label': '',
                    'description': '',
                    'speed': 0,
                    'duplex': None,
                    'module': None,
                    'enabled': True
                }

                # device = None

                # if initial_interface_values['device'] is not None:
                #     device = Device.objects.get(name=initial_interface_values['device'])

                # initial_interface_values['device'] = device

            total_errors = {}
            insert_data = []
            update_data = []
            total_data = []
            duplicates = []
            # Form validation 
            for record in request.data[::-1]:
                unique_interface = f'{record["name"]}/{record["hostname"]}'

                if unique_interface in duplicates:
                    continue
                duplicates.append(unique_interface)
                
                device = None
                try:
                    device = Device.objects.get(name=record['hostname'])
                except: 
                    device = None

                if device is None: 
                    continue
                record['device'] = device
                del record['hostname']

                if 'status' in record:
                    if record['status'] == 'up':
                        record['enabled'] = True
                    else:
                        record['enabled'] = False
                    del record['status']

                if 'description' in record:
                    record['description'] = str(record['description'])
                    
                new_data = {**initial_interface_values, **record}
                total_data.append(new_data)
       
            if enable_reconcile:
                batch_update_qs = []
                batch_insert_qs = []

                for item in total_data:
                    device = None

                    if item['device'] is not None:
                        device = Device.objects.get(name=item['device'])
                        
                    item['device'] = device

                    slurpit_interface_item = SlurpitInterface.objects.filter(name=item['name'], device=item['device'])
                    
                    if slurpit_interface_item:
                        slurpit_interface_item = slurpit_interface_item.first()

                        # Update
                        allowed_fields_with_none = {}
                        allowed_fields = {'duplex', 'label', 'description', 'speed', 'type', 'module', 'enabled'}
                        update = False
                        for field, value in item.items():
                            current = getattr(slurpit_interface_item, field, None)
                            if current != value:
                                if field in allowed_fields and value is not None and value != "":
                                    update = True
                                    setattr(slurpit_interface_item, field, value)
                                if field in allowed_fields_with_none:
                                    update = True
                                    setattr(slurpit_interface_item, field, value)
                        if update:
                            batch_update_qs.append(slurpit_interface_item)
                    else:
                        obj = Interface.objects.filter(name=item['name'], device=item['device'])
                        fields = {'label', 'device', 'module', 'type', 'duplex', 'speed', 'description', 'enabled'}
                        not_null_fields = {'label', 'device', 'module', 'type', 'duplex', 'speed', 'description', 'enabled'}

                        new_interface = {}
                        if obj:
                            obj = obj.first()
                            old_interface = {}

                            for field in fields:
                                field_name = f'ignore_{field}'
                                if field_name in interface_update_ignore_values:
                                    continue
                                old_interface[field] = getattr(obj, field)
                                new_interface[field] = item[field]

                                if field in not_null_fields and (new_interface[field] is None or new_interface[field] == ""):
                                    new_interface[field] = old_interface[field]

                            if new_interface == old_interface:
                                continue
                        else:
                            for field in fields: 
                                new_interface[field] = item[field]

                        batch_insert_qs.append(SlurpitInterface(
                            name = item['name'], 
                            **new_interface
                        ))
                
                count = len(batch_insert_qs)
                offset = 0

                while offset < count:
                    batch_qs = batch_insert_qs[offset:offset + BATCH_SIZE]
                    SlurpitInterface.objects.bulk_create(batch_qs)
                    offset += BATCH_SIZE


                count = len(batch_update_qs)
                offset = 0
                while offset < count:
                    batch_qs = batch_update_qs[offset:offset + BATCH_SIZE]
                    SlurpitInterface.objects.bulk_update(batch_qs, 
                        fields={'label', 'speed', 'type', 'duplex', 'description', 'module'}
                    )
                    offset += BATCH_SIZE

                duplicates = SlurpitInterface.objects.values('name', 'device_id').annotate(count=Count('id')).filter(count__gt=1)
                for duplicate in duplicates:
                    records = SlurpitInterface.objects.filter(name=duplicate['name'], device_id=duplicate['device_id'])                    
                    records.exclude(id=records.first().id).delete()
            else:                
                # Fail case
                for new_data in total_data:
                    obj = Interface()
                    form = InterfaceForm(data=new_data, instance=obj)
                    if form.is_valid() is False:
                        form_errors = form.errors
                        error_list_dict = {}

                        for field, errors in form_errors.items():
                            error_list_dict[field] = list(errors)

                        # Duplicate Interface
                        keys = error_list_dict.keys()
                        
                        if len(keys) ==1 and '__all__' in keys and len(error_list_dict['__all__']) == 1 and error_list_dict['__all__'][0].endswith("already exists."):
                            update_data.append(new_data)
                            continue
                        if '__all__' in keys and len(error_list_dict['__all__']) == 1 and error_list_dict['__all__'][0].endswith("already exists."):
                            del error_list_dict['__all__']
                        
                        error_key = f'{new_data["name"]}({"Global" if new_data["device"] is None else new_data["device"]})'
                        total_errors[error_key] = error_list_dict

                        return JsonResponse({'status': 'error', 'errors': total_errors}, status=400)
                    else:
                        insert_data.append(new_data)

                # Batch Insert
                count = len(insert_data)
                offset = 0
                while offset < count:
                    batch_qs = insert_data[offset:offset + BATCH_SIZE]
                    to_import = []        
                    for interface_item in batch_qs:
                        filtered_interface_item = {k: v for k, v in interface_item.items() if not k.startswith('ignore_')}
                        to_import.append(Interface(**filtered_interface_item))
                    Interface.objects.bulk_create(to_import)
                    offset += BATCH_SIZE
                
                
                # Batch Update
                batch_update_qs = []
                for update_item in update_data:
                    item = Interface.objects.get(name=update_item['name'], device=update_item['device'])
                    
                    # Update
                    allowed_fields_with_none = {}
                    allowed_fields = {'duplex', 'label', 'speed', 'type', 'description', 'module'}

                    for field, value in update_item.items():
                        ignore_field = f'ignore_{field}'
                        if ignore_field in interface_update_ignore_values:
                            continue 

                        if field in allowed_fields and value is not None and value != "":
                            setattr(item, field, value)
                        if field in allowed_fields_with_none:
                            setattr(item, field, value)

                    batch_update_qs.append(item)

                
                count = len(batch_update_qs)
                offset = 0
                while offset < count:
                    batch_qs = batch_update_qs[offset:offset + BATCH_SIZE]
                    to_import = []        
                    for interface_item in batch_qs:
                        to_import.append(interface_item)

                    Interface.objects.bulk_update(to_import, 
                        fields={'label', 'speed', 'type', 'duplex', 'description', 'module'}
                    )
                    offset += BATCH_SIZE


            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'errors', 'errors': f"Process threw error: {e} - {traceback.format_exc()}"}, status=400)
        
class SlurpitIPAMView(SlurpitViewSet):
    queryset = IPAddress.objects.all()
    
    def get_serializer_class(self):
        return SlurpitInitIPAddressSerializer
    
    def create(self, request):
        # Validate request IPAM data
        errors = ipam_validator(request.data)
        if errors:
            return JsonResponse({'status': 'error', 'errors': errors}, status=400)

        vrf = None
        tenant = None

        try:
            # Get initial values for IPAM
            enable_reconcile = True
            initial_obj = SlurpitInitIPAddress.objects.filter(address=None).values(
                'status', 'vrf', 'tenant', 'role', 'enable_reconcile', 'description', 'ignore_status', 'ignore_vrf', 'ignore_tenant', 'ignore_role', 'ignore_description'
            ).first()

            initial_ipaddress_values = {}
            ipaddress_update_ignore_values = []
            vrf = None
            tenant = None
            if initial_obj:
                enable_reconcile = initial_obj['enable_reconcile']
                del initial_obj['enable_reconcile']
                initial_ipaddress_values = {**initial_obj}

                obj = SlurpitInitIPAddress.objects.filter(address=None).get()

                if initial_ipaddress_values['vrf'] is not None:
                    vrf = VRF.objects.get(pk=initial_ipaddress_values['vrf'])
                if initial_ipaddress_values['tenant'] is not None:
                    tenant = Tenant.objects.get(pk=initial_ipaddress_values['tenant'])

                initial_ipaddress_values['vrf'] = vrf
                initial_ipaddress_values['tenant'] = tenant

                for key in initial_ipaddress_values.keys():
                    if key.startswith('ignore_') and initial_ipaddress_values[key]:
                        ipaddress_update_ignore_values.append(key)
                
            else:
                initial_ipaddress_values['vrf'] = None
                initial_ipaddress_values['tenant'] = None
                initial_ipaddress_values['role'] = ''
                initial_ipaddress_values['description'] = ''
                initial_ipaddress_values['status'] = 'active'

            total_errors = {}
            insert_ips = []
            update_ips = []
            total_ips = []

            duplicates = []
            # Form validation 
            for record in request.data[::-1]:
                unique_ipaddress = f'{record["address"]}'

                if unique_ipaddress in duplicates:
                    continue
                duplicates.append(unique_ipaddress)

                new_data = {**initial_ipaddress_values, **record}
                total_ips.append(new_data)



            if enable_reconcile:
                batch_update_qs = []
                batch_insert_qs = []

                for item in total_ips:

                    slurpit_ipaddress_item = SlurpitInitIPAddress.objects.filter(address=item['address'], vrf=item['vrf'])
                    
                    if slurpit_ipaddress_item:
                        slurpit_ipaddress_item = slurpit_ipaddress_item.first()

                        allowed_fields_with_none = {'status'}
                        allowed_fields = {'role', 'tenant', 'dns_name', 'description'}
                        update = False
                        for field, value in item.items():
                            current = getattr(slurpit_ipaddress_item, field, None)
                            if current != value:
                                if field in allowed_fields and value is not None and value != "":
                                    update = True
                                    setattr(slurpit_ipaddress_item, field, value)
                                if field in allowed_fields_with_none:
                                    update = True
                                    setattr(slurpit_ipaddress_item, field, value)
                        if update:
                            batch_update_qs.append(slurpit_ipaddress_item)
                    else:
                        obj = IPAddress.objects.filter(address=item['address'], vrf=vrf)
                        fields = ['status', 'role', 'description', 'tenant', 'dns_name']
                        not_null_fields = {'role', 'description', 'tenant', 'dns_name'}
                        new_ipaddress = {}

                        if obj:
                            obj = obj.first()
                            old_ipaddress = {}
                            
                            for field in fields:
                                field_name = f'ignore_{field}'
                                if field_name in ipaddress_update_ignore_values:
                                    continue
                                old_ipaddress[field] = getattr(obj, field)
                                new_ipaddress[field] = item[field]

                                if field in not_null_fields and (new_ipaddress[field] is None or new_ipaddress[field] == ""):
                                    new_ipaddress[field] = old_ipaddress[field]

                            if new_ipaddress == old_ipaddress:
                                continue
                        else:
                            for field in fields:
                                new_ipaddress[field] = item[field]
                        
                        obj = SlurpitInitIPAddress(
                            address = item['address'], 
                            vrf = vrf,
                            **new_ipaddress
                        )

                        batch_insert_qs.append(obj)
                
                count = len(batch_insert_qs)
                offset = 0

                while offset < count:
                    batch_qs = batch_insert_qs[offset:offset + BATCH_SIZE]
                    created_items = SlurpitInitIPAddress.objects.bulk_create(batch_qs)
                    offset += BATCH_SIZE

                count = len(batch_update_qs)
                offset = 0
                while offset < count:
                    batch_qs = batch_update_qs[offset:offset + BATCH_SIZE]
                    SlurpitInitIPAddress.objects.bulk_update(batch_qs, fields={'status', 'role', 'tenant', 'dns_name', 'description'})
                    offset += BATCH_SIZE

                duplicates = SlurpitInitIPAddress.objects.values('address', 'vrf').annotate(count=Count('id')).filter(count__gt=1)
                for duplicate in duplicates:
                    records = SlurpitInitIPAddress.objects.filter(address=duplicate['address'], vrf=duplicate['vrf'])                    
                    records.exclude(id=records.first().id).delete()
                
            else:
                # Fail case
                for new_data in total_ips:
                    obj = IPAddress()
                    form = IPAddressForm(data=new_data, instance=obj)
                    if form.is_valid() is False:
                        form_errors = form.errors
                        error_list_dict = {}

                        for field, errors in form_errors.items():
                            error_list_dict[field] = list(errors)

                        # Duplicate IP Address
                        keys = error_list_dict.keys()
                        
                        if len(keys) ==1 and 'address' in keys and len(error_list_dict['address']) == 1 and error_list_dict['address'][0].startswith("Duplicate"):
                            update_ips.append(new_data)
                            continue
                        if 'address' in keys and len(error_list_dict['address']) == 1 and error_list_dict['address'][0].startswith("Duplicate"):
                            del error_list_dict['address']
                        
                        error_key = f'{new_data["address"]}({"Global" if new_data["vrf"] is None else new_data["vrf"]})'
                        total_errors[error_key] = error_list_dict

                        return JsonResponse({'status': 'error', 'errors': total_errors}, status=400)
                    else:
                        insert_ips.append(new_data)

                # Batch Insert
                count = len(insert_ips)
                offset = 0
                while offset < count:
                    batch_qs = insert_ips[offset:offset + BATCH_SIZE]
                    to_import = []        
                    for ipaddress_item in batch_qs:
                        filtered_ipaddress_item = {k: v for k, v in ipaddress_item.items() if not k.startswith('ignore_')}
                        to_import.append(IPAddress(**filtered_ipaddress_item))

                    IPAddress.objects.bulk_create(to_import)
                    offset += BATCH_SIZE
                
                # Batch Update
                batch_update_qs = []
                for update_item in update_ips:
                    item = IPAddress.objects.get(address=update_item['address'], vrf=update_item['vrf'])

                    # Update
                    allowed_fields_with_none = {'status'}
                    allowed_fields = {'role', 'tenant', 'dns_name', 'description'}

                    for field, value in update_item.items():
                        ignore_field = f'ignore_{field}'
                        if ignore_field in ipaddress_update_ignore_values:
                            continue 

                        if field in allowed_fields and value is not None and value != "":
                            setattr(item, field, value)
                        if field in allowed_fields_with_none:
                            setattr(item, field, value)

                    batch_update_qs.append(item)

                count = len(batch_update_qs)
                offset = 0
                while offset < count:
                    batch_qs = batch_update_qs[offset:offset + BATCH_SIZE]

                    IPAddress.objects.bulk_update(batch_qs, fields={'status', 'role', 'tenant', 'dns_name', 'description'})
                    offset += BATCH_SIZE


            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'errors': str(e)}, status=400)
        


class SlurpitPrefixView(SlurpitViewSet):
    queryset = SlurpitPrefix.objects.all()

    def get_serializer_class(self):
        return SlurpitPrefixSerializer
    
    def create(self, request):
        # Validate request prefix data
        errors = prefix_validator(request.data)
        if errors:
            return JsonResponse({'status': 'error', 'errors': errors}, status=400)

        vrf = None
        tenant = None
        vlan = None
        role = None
        site = None
        site_group = None
        location = None
        region = None
            
        try:
            # Get initial values for prefix
            enable_reconcile = True
            initial_obj = SlurpitPrefix.objects.filter(prefix=None).values(
                'status', 'vrf', 'role', 'vlan', 'tenant', 'enable_reconcile', 'description', 'ignore_status', 'ignore_vrf', 'ignore_role', 'ignore_site', 'ignore_vlan', 'ignore_tenant', 'ignore_description', '_site', '_site_group', '_region', '_location'
            ).first()
            initial_prefix_values = {}
            prefix_update_ignore_values = []

            if initial_obj:
                enable_reconcile = initial_obj['enable_reconcile']
                del initial_obj['enable_reconcile']
                initial_prefix_values = {**initial_obj}

                if initial_prefix_values['vrf'] is not None:
                    vrf = VRF.objects.get(pk=initial_prefix_values['vrf'])
                if initial_prefix_values['tenant'] is not None:
                    tenant = Tenant.objects.get(pk=initial_prefix_values['tenant'])
                if initial_prefix_values['vlan'] is not None:
                    vlan = VLAN.objects.get(pk=initial_prefix_values['vlan'])
                if initial_prefix_values['role'] is not None:
                    role = Role.objects.get(pk=initial_prefix_values['role'])
                if initial_prefix_values['_site'] is not None:
                    site = Site.objects.get(pk=initial_prefix_values['_site'])
                if initial_prefix_values['_site_group'] is not None:
                    site_group = SiteGroup.objects.get(pk=initial_prefix_values['_site_group'])
                if initial_prefix_values['_location'] is not None:
                    location = Location.objects.get(pk=initial_prefix_values['_location'])
                if initial_prefix_values['_region'] is not None:
                    region = Region.objects.get(pk=initial_prefix_values['_region'])

                initial_prefix_values['vrf'] = vrf
                initial_prefix_values['tenant'] = tenant
                initial_prefix_values['vlan'] = vlan
                initial_prefix_values['role'] = role
                initial_prefix_values['_site'] = site
                initial_prefix_values['_site_group'] = site_group
                initial_prefix_values['_location'] = location
                initial_prefix_values['_region'] = region

                for key in initial_prefix_values.keys():
                    if key.startswith('ignore_') and initial_prefix_values[key]:
                        prefix_update_ignore_values.append(key)

            else:
                initial_prefix_values = {
                    'status': 'active',
                    'vrf': None,
                    '_site': None,
                    '_site_group': None,
                    '_location': None,
                    '_region': None,
                    'tenant': None,
                    'vlan': None,
                    'role': None,
                    'description': ''
                }

            total_errors = {}
            insert_data = []
            update_data = []
            total_data = []

            duplicates = []
            # Form validation 
            for record in request.data[::-1]:
                unique_prefix = f'{record["prefix"]}'

                if unique_prefix in duplicates:
                    continue
                duplicates.append(unique_prefix)

                if 'vrf' in record and len(record['vrf']) > 0:
                    vrf = VRF.objects.filter(name=record['vrf'])
                    if vrf:
                        record['vrf'] = vrf.first()
                    else:
                        vrf = VRF.objects.create(name=record['vrf'])
                        record['vrf'] = vrf
                else:
                    if 'vrf' in record:
                        del record['vrf']

                new_data = {**initial_prefix_values, **record}
                total_data.append(new_data)
        
            if enable_reconcile:
                batch_update_qs = []
                batch_insert_qs = []

                for item in total_data:

                    slurpit_prefix_item = SlurpitPrefix.objects.filter(prefix=item['prefix'], vrf=item['vrf'])
                    
                    if slurpit_prefix_item:
                        slurpit_prefix_item = slurpit_prefix_item.first()

                        allowed_fields_with_none = {'status'}
                        allowed_fields = {'role', 'tenant', 'vlan', 'vrf', 'description', '_site', '_site_group', '_location', '_region'}
                        update = False
                        for field, value in item.items():
                            current = getattr(slurpit_prefix_item, field, None)
                            if current != value:
                                if field in allowed_fields and value is not None and value != "":
                                    update = True
                                    setattr(slurpit_prefix_item, field, value)
                                if field in allowed_fields_with_none:
                                    update = True
                                    setattr(slurpit_prefix_item, field, value)
                        if update:
                            batch_update_qs.append(slurpit_prefix_item)
                    else:
                        obj = Prefix.objects.filter(prefix=item['prefix'], vrf=item['vrf'])
                        
                        fields = {'status', 'vrf', 'vlan', 'tenant', 'role', 'description', '_site', '_site_group', '_location', '_region'}
                        not_null_fields = {'vlan', 'tenant', 'role', 'description', '_site', '_site_group', '_location', '_region'}
                        
                        new_prefix = {}

                        if obj:
                            obj = obj.first()
                            old_prefix = {}
                            
                            for field in fields:
                                field_name = f'ignore_{field}'
                                if field_name in prefix_update_ignore_values:
                                    continue
                                old_prefix[field] = getattr(obj, field)
                                new_prefix[field] = item[field]

                                if field in not_null_fields and (new_prefix[field] is None or new_prefix[field] == ""):
                                    new_prefix[field] = old_prefix[field]

                            if new_prefix == old_prefix:
                                continue
                        else:
                            for field in fields:
                                new_prefix[field] = item[field]

                        batch_insert_qs.append(SlurpitPrefix(
                            prefix = item['prefix'],
                            **new_prefix
                        ))
                
                count = len(batch_insert_qs)
                offset = 0

                while offset < count:
                    batch_qs = batch_insert_qs[offset:offset + BATCH_SIZE]
                    SlurpitPrefix.objects.bulk_create(batch_qs)
                    offset += BATCH_SIZE


                count = len(batch_update_qs)
                offset = 0
                while offset < count:
                    batch_qs = batch_update_qs[offset:offset + BATCH_SIZE]
                    SlurpitPrefix.objects.bulk_update(batch_qs, fields={'description', 'vrf', 'tenant', 'status', 'vlan', 'role', '_site', '_site_group', '_location', '_region'})
                    offset += BATCH_SIZE

                duplicates = SlurpitPrefix.objects.values('prefix', 'vrf').annotate(count=Count('id')).filter(count__gt=1)
                for duplicate in duplicates:
                    records = SlurpitPrefix.objects.filter(prefix=duplicate['prefix'], vrf=duplicate['vrf'])                    
                    records.exclude(id=records.first().id).delete()

            else:                
                # Fail case
                for new_data in total_data:
                    obj = Prefix()
                    form = PrefixForm(data=new_data, instance=obj)
                    if form.is_valid() is False:
                        form_errors = form.errors
                        error_list_dict = {}

                        for field, errors in form_errors.items():
                            error_list_dict[field] = list(errors)

                        # Duplicate Prefix
                        keys = error_list_dict.keys()
                        
                        if len(keys) ==1 and 'prefix' in keys and len(error_list_dict['prefix']) == 1 and error_list_dict['prefix'][0].startswith("Duplicate"):
                            update_data.append(new_data)
                            continue
                        if 'prefix' in keys and len(error_list_dict['prefix']) == 1 and error_list_dict['prefix'][0].startswith("Duplicate"):
                            del error_list_dict['prefix']
                        
                        error_key = f'{new_data["prefix"]}({"Global" if new_data["vrf"] is None else new_data["vrf"]})'
                        total_errors[error_key] = error_list_dict

                        return JsonResponse({'status': 'error', 'errors': total_errors}, status=400)
                    else:
                        insert_data.append(new_data)

                # Batch Insert
                count = len(insert_data)
                offset = 0
                while offset < count:
                    batch_qs = insert_data[offset:offset + BATCH_SIZE]
                    to_import = []        
                    for prefix_item in batch_qs:
                        filtered_prefix_item = {k: v for k, v in prefix_item.items() if not k.startswith('ignore_')}
                        to_import.append(Prefix(**filtered_prefix_item))
                    Prefix.objects.bulk_create(to_import)
                    offset += BATCH_SIZE
                
                
                # Batch Update
                batch_update_qs = []
                for update_item in update_data:
                    item = Prefix.objects.get(prefix=update_item['prefix'], vrf=update_item['vrf'])
                    
                    # Update
                    allowed_fields_with_none = {'status'}
                    allowed_fields = {'role', 'tenant', 'vlan', 'description', 'vrf', '_site', '_site_group', '_location', '_region'}

                    for field, value in update_item.items():
                        ignore_field = f'ignore_{field}'
                        if ignore_field in prefix_update_ignore_values:
                            continue 
                        
                        if field in allowed_fields and value is not None and value != "":
                            setattr(item, field, value)
                        if field in allowed_fields_with_none:
                            setattr(item, field, value)
                    
                    batch_update_qs.append(item)

                
                count = len(batch_update_qs)
                offset = 0
                while offset < count:
                    batch_qs = batch_update_qs[offset:offset + BATCH_SIZE]
                    to_import = []        
                    for prefix_item in batch_qs:
                        to_import.append(prefix_item)

                    Prefix.objects.bulk_update(to_import, 
                        fields={
                            'description', 'vrf', 'tenant', 'status', 'vlan', 'role', '_site', '_site_group', '_location', '_region'
                        }
                    )
                    offset += BATCH_SIZE


            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'errors', 'errors': f"Process threw error: {e} - {traceback.format_exc()}"}, status=400)

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request, *args, **kwargs):
        prefixes = Prefix.objects.filter(tags__name="slurpit")
        serializer = PrefixSerializer(prefixes, many=True, context={'request': request})
        
        prefixes = []
        for prefix in serializer.data:
            prefixes.append(f'{prefix["prefix"]}')
        return JsonResponse(prefixes, safe=False)

class SlurpitVLANView(SlurpitViewSet):
    queryset = SlurpitVLAN.objects.all()

    def get_serializer_class(self):
        return SlurpitVLANSerializer
    
    def create(self, request):
        # Validate request vlan data
        errors = vlan_validator(request.data)
        if errors:
            return JsonResponse({'status': 'error', 'errors': errors}, status=400)

        tenant = None
        role = None
            
        try:
            # Get initial values for vlan
            enable_reconcile = True
            initial_obj = SlurpitVLAN.objects.filter(name='').values(
                'status', 'role', 'tenant', 'enable_reconcile', 'description', 
                'ignore_status', 'ignore_role', 'ignore_tenant', 'ignore_description'
            ).first()
            initial_vlan_values = {}
            vlan_update_ignore_values = []

            if initial_obj:
                enable_reconcile = initial_obj['enable_reconcile']
                del initial_obj['enable_reconcile']
                initial_vlan_values = {**initial_obj}

                if initial_vlan_values['tenant'] is not None:
                    tenant = Tenant.objects.get(pk=initial_vlan_values['tenant'])
                if initial_vlan_values['role'] is not None:
                    role = Role.objects.get(pk=initial_vlan_values['role'])

                initial_vlan_values['tenant'] = tenant
                initial_vlan_values['role'] = role

                for key in initial_vlan_values.keys():
                    if key.startswith('ignore_') and initial_vlan_values[key]:
                        vlan_update_ignore_values.append(key)

            else:
                initial_vlan_values = {
                    'status': 'active',
                    'tenant': None,
                    'role': None,
                    'description': ''
                }

            total_errors = {}
            insert_data = []
            update_data = []
            total_data = []

            duplicates = []
            # Form validation 
            for record in request.data[::-1]:
                unique_group_name = f'{record["hostname"]}_{record["vlan_name"]}'
                unique_group_id = f'{record["hostname"]}_{record["vlan_id"]}'
                if unique_group_name in duplicates or unique_group_id in duplicates:
                    continue
                duplicates.append(unique_group_name)
                duplicates.append(unique_group_id)


                new_data = {
                    **initial_vlan_values, 
                    "vid": record['vlan_id'],
                    "name": record['vlan_name'],
                    "hostname": record['hostname']
                }
                # Get VLANGroup ID 
                group = VLANGroup.objects.filter(name=record['hostname'])
                if group:
                    group = group.first()
                    new_data['group'] = group
                total_data.append(new_data)
        
            if enable_reconcile:
                batch_update_qs = []
                batch_insert_qs = []

                for item in total_data:
                    slurpit_vlan_item = SlurpitVLAN.objects.filter(name=item['name'], group=item['hostname'])
                    if not slurpit_vlan_item:
                        slurpit_vlan_item = SlurpitVLAN.objects.filter(vid=item['vid'], group=item['hostname'])

                    if slurpit_vlan_item:
                        slurpit_vlan_item = slurpit_vlan_item.first()

                        allowed_fields_with_none = {'status'}
                        allowed_fields = {'role', 'tenant', 'description'}
                        update = False

                        for field, value in item.items():
                            current = getattr(slurpit_vlan_item, field, None)
                            if current != value:
                                if field in allowed_fields and value is not None and value != "":
                                    update = True
                                    setattr(slurpit_vlan_item, field, value)
                                if field in allowed_fields_with_none:
                                    update = True
                                    setattr(slurpit_vlan_item, field, value)
                        if update:
                            batch_update_qs.append(slurpit_vlan_item)
                    else:
                        obj = VLAN.objects.filter(name=item['name'], group__name=item['hostname'])
                        if not obj:
                            obj = VLAN.objects.filter(vid=item['vid'], group__name=item['hostname'])

                        fields = {'status', 'tenant', 'role', 'description', 'name'}
                        not_null_fields = {'tenant', 'role', 'description'}
                        
                        new_vlan = {}

                        if obj:
                            obj = obj.first()
                            old_vlan = {}
                            
                            for field in fields:
                                field_name = f'ignore_{field}'
                                if field_name in vlan_update_ignore_values:
                                    continue
                                old_vlan[field] = getattr(obj, field)
                                new_vlan[field] = item[field]

                                if field in not_null_fields and (new_vlan[field] is None or new_vlan[field] == ""):
                                    new_vlan[field] = old_vlan[field]

                            if new_vlan == old_vlan:
                                continue
                        else:
                            for field in fields:
                                new_vlan[field] = item[field]

                        batch_insert_qs.append(SlurpitVLAN(
                            # name = item['name'],
                            vid = item['vid'],
                            group = item['hostname'],
                            **new_vlan
                        ))
                
                count = len(batch_insert_qs)
                offset = 0

                while offset < count:
                    batch_qs = batch_insert_qs[offset:offset + BATCH_SIZE]
                    SlurpitVLAN.objects.bulk_create(batch_qs)
                    offset += BATCH_SIZE


                count = len(batch_update_qs)
                offset = 0
                while offset < count:
                    batch_qs = batch_update_qs[offset:offset + BATCH_SIZE]
                    SlurpitVLAN.objects.bulk_update(batch_qs, fields={'description', 'tenant', 'status', 'role'})
                    offset += BATCH_SIZE

                duplicates = SlurpitVLAN.objects.values('name', 'group').annotate(count=Count('id')).filter(count__gt=1)
                for duplicate in duplicates:
                    records = SlurpitVLAN.objects.filter(name=duplicate['name'], group=duplicate['hostname'])                    
                    records.exclude(id=records.first().id).delete()

                duplicates = SlurpitVLAN.objects.values('vid', 'group').annotate(count=Count('id')).filter(count__gt=1)
                for duplicate in duplicates:
                    records = SlurpitVLAN.objects.filter(vid=duplicate['vid'], group=duplicate['hostname'])                    
                    records.exclude(id=records.first().id).delete()

            else:                
                # Fail case
                for new_data in total_data:
                    obj = VLAN()
                    form = VLANForm(data=new_data, instance=obj)
                    if form.is_valid() is False:
                        form_errors = form.errors
                        error_list_dict = {}

                        for field, errors in form_errors.items():
                            error_list_dict[field] = list(errors)

                        # Duplicate VLAN
                        keys = error_list_dict.keys()

                        if len(keys) ==1 and '__all__' in keys:
                            flag = True
                            for errorItem in error_list_dict['__all__']:
                                if not errorItem.endswith("already exists."):
                                    flag = False
                                    break
                            if flag:
                                update_data.append(new_data)
                                continue
                        if '__all__' in keys:
                            del error_list_dict['__all__']
                        
                        error_key = f'{new_data["name"]}({new_data["vid"]})'
                        total_errors[error_key] = error_list_dict

                        return JsonResponse({'status': 'error', 'errors': total_errors}, status=400)
                    else:
                        insert_data.append(new_data)

                # Batch Insert
                count = len(insert_data)
                offset = 0
                while offset < count:
                    batch_qs = insert_data[offset:offset + BATCH_SIZE]
                    to_import = []        
                    for vlan_item in batch_qs:
                        filtered_vlan_item = {k: v for k, v in vlan_item.items() if not k.startswith('ignore_')}
                        if not 'group' in filtered_vlan_item:
                            vlan_group = VLANGroup.objects.create(name=filtered_vlan_item['hostname'],slug=filtered_vlan_item['hostname'])
                            filtered_vlan_item['group'] = vlan_group
                        del filtered_vlan_item['hostname']
                        to_import.append(VLAN(**filtered_vlan_item))
                    VLAN.objects.bulk_create(to_import)
                    offset += BATCH_SIZE
                
                # Batch Update
                batch_update_qs = []
                for update_item in update_data:
                    if not 'group' in update_item:
                        vlan_group = VLANGroup.objects.create(name=update_item['hostname'],slug=update_item['hostname'])
                        update_item['group'] = vlan_group

                    item = VLAN.objects.filter(name=update_item['name'], group=update_item['group'])
                    if not item:
                        item = VLAN.objects.filter(vid=update_item['vid'], group=update_item['group'])

                    if item:
                        item = item.first()
                    # Update
                    allowed_fields_with_none = {'status'}
                    allowed_fields = {'role', 'tenant', 'description', 'name'}

                    for field, value in update_item.items():
                        ignore_field = f'ignore_{field}'
                        if ignore_field in vlan_update_ignore_values:
                            continue 
                        
                        if field in allowed_fields and value is not None and value != "":
                            setattr(item, field, value)
                        if field in allowed_fields_with_none:
                            setattr(item, field, value)
                    
                    batch_update_qs.append(item)

                
                count = len(batch_update_qs)
                offset = 0
                while offset < count:
                    batch_qs = batch_update_qs[offset:offset + BATCH_SIZE]
                    to_import = []        
                    for vlan_item in batch_qs:
                        to_import.append(vlan_item)

                    VLAN.objects.bulk_update(to_import, 
                        fields={
                            'description', 'tenant', 'status', 'role', 'name'
                        }
                    )
                    offset += BATCH_SIZE


            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'errors', 'errors': str(e)}, status=400)

class SlurpitPlanningViewSet(
        SlurpitViewSet
    ):
    queryset = SlurpitPlanning.objects.all()
    serializer_class = SlurpitPlanningSerializer
    filterset_class = SlurpitPlanningFilterSet
    
    def get_queryset(self):
        if self.request.method == 'GET':
            # Customize this queryset to suit your requirements for GET requests
            return SlurpitPlanning.objects.filter(selected=True)
        # For other methods, use the default queryset
        return self.queryset
    
class SlurpitSiteView(SlurpitViewSet):
    queryset = Site.objects.all()
    
    def get_serializer_class(self):
        return SiteSerializer
    
    def create(self, request):
        try:
            create_sites(request.data[::-1])
        except Exception as e:
            return JsonResponse({'status': 'errors', 'errors': str(e)}, status=400)

        return JsonResponse({'status': 'success'})
        
