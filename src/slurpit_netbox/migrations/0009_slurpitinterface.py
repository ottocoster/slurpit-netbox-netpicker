# Generated by Django 4.2.9 on 2024-04-30 03:16

import dcim.fields
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import taggit.managers
import utilities.fields
import utilities.json
import utilities.ordering
import utilities.tracking


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0105_customfield_min_max_values'),
        ('dcim', '0185_gfk_indexes'),
        ('slurpit_netbox', '0008_slurpitinitipaddress_address_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SlurpitInterface',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('cable_end', models.CharField(blank=True, max_length=1)),
                ('mark_connected', models.BooleanField(default=False)),
                ('enabled', models.BooleanField(default=True)),
                ('mac_address', dcim.fields.MACAddressField(blank=True, null=True)),
                ('mtu', models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(65536)])),
                ('mode', models.CharField(blank=True, max_length=50)),
                ('name', models.CharField(max_length=64)),
                ('label', models.CharField(blank=True, max_length=64)),
                ('description', models.CharField(blank=True, max_length=200)),
                ('_name', utilities.fields.NaturalOrderingField('name', blank=True, max_length=100, naturalize_function=utilities.ordering.naturalize_interface)),
                ('type', models.CharField(max_length=50)),
                ('speed', models.PositiveIntegerField(blank=True, null=True)),
                ('duplex', models.CharField(blank=True, max_length=50, null=True)),
                ('enable_reconcile', models.BooleanField(default=False)),
                ('_path', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='dcim.cablepath')),
                ('bridge', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bridge_interfaces', to='slurpit_netbox.slurpitinterface')),
                ('cable', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='dcim.cable')),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)ss', to='dcim.device')),
                ('module', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='%(class)ss', to='dcim.module')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='child_interfaces', to='slurpit_netbox.slurpitinterface')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'Slurpit Device Interface',
                'verbose_name_plural': 'Slurpit Device Interface',
            },
            bases=(models.Model, utilities.tracking.TrackingModelMixin),
        ),
    ]
