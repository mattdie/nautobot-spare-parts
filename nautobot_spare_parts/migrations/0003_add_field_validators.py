import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_spare_parts", "0002_spareparttransaction_jira_ticket"),
    ]

    operations = [
        migrations.AlterField(
            model_name="spareparttype",
            name="unit_cost",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Cost per unit in local currency",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="spareparttransaction",
            name="jira_ticket",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Jira ticket reference (e.g. INFRA2-1234)",
                max_length=50,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Jira ticket must look like INFRA2-1234",
                        regex="^[A-Z][A-Z0-9]*-\\d+$",
                    )
                ],
            ),
        ),
    ]
