import django.db.models.deletion
from django.db import migrations, models


def populate_denormalized_fields(apps, schema_editor):
    """
    Copy site ForeignKey values to the scope GFK.
    """
    SlurpitPrefix = apps.get_model('slurpit_netbox', 'SlurpitPrefix')

    prefixes = SlurpitPrefix.objects.filter(site__isnull=False).prefetch_related('site')
    for prefix in prefixes:
        prefix._region_id = prefix.site.region_id
        prefix._site_group_id = prefix.site.group_id
        prefix._site_id = prefix.site_id

    SlurpitPrefix.objects.bulk_update(prefixes, ['_region', '_site_group', '_site'])


class Migration(migrations.Migration):
    dependencies = [
        ('slurpit_netbox', '0024_alter_slurpitprefix_scope'),
    ]

    operations = [
        migrations.AddField(
            model_name='slurpitprefix',
            name='_location',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dcim.location'
            ),
        ),
        migrations.AddField(
            model_name='slurpitprefix',
            name='_region',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dcim.region'
            ),
        ),
        migrations.AddField(
            model_name='slurpitprefix',
            name='_site',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dcim.site'),
        ),
        migrations.AddField(
            model_name='slurpitprefix',
            name='_site_group',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dcim.sitegroup'
            ),
        ),
        # Populate denormalized FK values
        migrations.RunPython(code=populate_denormalized_fields, reverse_code=migrations.RunPython.noop),
        # Delete the site ForeignKey
        migrations.RemoveField(
            model_name='slurpitprefix',
            name='site',
        ),
    ]
