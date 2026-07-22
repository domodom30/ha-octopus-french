"""Test configuration for Octopus French Energy."""

import pytest


@pytest.fixture
def _recorder_before_hass(request: pytest.FixtureRequest) -> None:
    """Instancie la base du recorder avant ``hass`` quand ``recorder_mock`` est utilisé.

    ``recorder_db_url`` (pytest-homeassistant-custom-component) exige d'être créée
    avant la fixture ``hass`` ; or ``auto_enable_custom_integrations`` (autouse)
    crée ``hass`` en premier. On force donc l'ordre ici.
    """
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_db_url")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(_recorder_before_hass, enable_custom_integrations):
    """Rend l'intégration custom chargeable dans tous les tests.

    Dépend de la fixture ``enable_custom_integrations`` fournie par
    ``pytest-homeassistant-custom-component`` — on ne la redéfinit pas (sinon on la masque).
    """
    yield
