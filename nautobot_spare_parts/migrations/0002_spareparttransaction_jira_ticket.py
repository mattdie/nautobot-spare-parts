from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_spare_parts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="spareparttransaction",
            name="jira_ticket",
            field=models.CharField(
                blank=True,
                help_text="Jira ticket ID (e.g., INFRA2-11604)",
                max_length=50,
            ),
        ),
    ]
