"""SAML sign-in, tested against a fake identity provider that signs real
assertions with a throwaway certificate (no network)."""
import base64
import datetime as dt
import uuid
from urllib.parse import parse_qs, urlsplit
import zlib

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from onelogin.saml2.constants import OneLogin_Saml2_Constants as C
from onelogin.saml2.utils import OneLogin_Saml2_Utils
from sqlalchemy import select

from app.extensions import db
from app.models import User

from .conftest import login, make_user

IDP_ENTITY = "https://portal.sso.example.aws/saml/assertion/TEST"
IDP_SSO = "https://portal.sso.example.aws/saml/assertion/TEST/login"
ACS = "http://localhost/login/saml/acs"
SP_ENTITY = "http://localhost/saml/metadata"


def _keypair(cn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30)).sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption()).decode()
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key_pem, cert_pem


IDP_KEY, IDP_CERT = _keypair("fake-idp")
OTHER_KEY, OTHER_CERT = _keypair("attacker")


def _cert_body(pem):
    return "".join(line for line in pem.splitlines() if "CERTIFICATE" not in line)


def idp_metadata():
    return f"""<?xml version="1.0"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{IDP_ENTITY}">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing"><ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#"><ds:X509Data>
      <ds:X509Certificate>{_cert_body(IDP_CERT)}</ds:X509Certificate></ds:X509Data></ds:KeyInfo></md:KeyDescriptor>
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="{IDP_SSO}"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>"""


def _ts(delta=0):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_response(in_response_to, name_id="u-123", email="pat@college.example", *, audience=SP_ENTITY,
                  issuer=IDP_ENTITY, key=IDP_KEY, cert=IDP_CERT, sign=True, not_after=300):
    aid = "_" + uuid.uuid4().hex
    irt = f' InResponseTo="{in_response_to}"' if in_response_to else ""
    attrs = (f'<saml:AttributeStatement><saml:Attribute Name="email"><saml:AttributeValue>{email}'
             '</saml:AttributeValue></saml:Attribute></saml:AttributeStatement>') if email else ""
    assertion = f"""<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="{aid}" Version="2.0" IssueInstant="{_ts()}">
<saml:Issuer>{issuer}</saml:Issuer>
<saml:Subject><saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">{name_id}</saml:NameID>
<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"><saml:SubjectConfirmationData NotOnOrAfter="{_ts(not_after)}" Recipient="{ACS}"{irt}/></saml:SubjectConfirmation></saml:Subject>
<saml:Conditions NotBefore="{_ts(-60)}" NotOnOrAfter="{_ts(not_after)}"><saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction></saml:Conditions>
<saml:AuthnStatement AuthnInstant="{_ts()}" SessionIndex="{aid}"><saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef></saml:AuthnContext></saml:AuthnStatement>
{attrs}
</saml:Assertion>"""
    if sign:
        assertion = OneLogin_Saml2_Utils.add_sign(assertion, key, cert, sign_algorithm=C.RSA_SHA256,
                                                  digest_algorithm=C.SHA256)
        assertion = assertion.decode() if isinstance(assertion, bytes) else assertion
        assertion = assertion.split("?>", 1)[-1] if assertion.startswith("<?xml") else assertion
    response = f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_{uuid.uuid4().hex}" Version="2.0" IssueInstant="{_ts()}" Destination="{ACS}"{irt}>
<saml:Issuer>{issuer}</saml:Issuer><samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
{assertion}</samlp:Response>"""
    return base64.b64encode(response.encode()).decode()


@pytest.fixture()
def saml_app(app, tmp_path):
    meta = tmp_path / "idp.xml"
    meta.write_text(idp_metadata())
    app.config["SAML_IDP_METADATA_FILE"] = str(meta)
    app.extensions.pop("merchant_saml", None)
    return app


def start(client, next_url=None):
    resp = client.get("/login/saml" + (f"?next={next_url}" if next_url else ""))
    assert resp.status_code == 302 and resp.headers["Location"].startswith(IDP_SSO)
    q = parse_qs(urlsplit(resp.headers["Location"]).query)
    xml = zlib.decompress(base64.b64decode(q["SAMLRequest"][0]), -15).decode()
    request_id = xml.split('ID="', 1)[1].split('"', 1)[0]
    return request_id, q["RelayState"][0]


def post_back(client, saml_response, relay):
    return client.post("/login/saml/acs", data={"SAMLResponse": saml_response, "RelayState": relay})


def test_button_and_routes_only_when_configured(app, client):
    assert b"Sign in with AWS" not in client.get("/login").data
    assert client.get("/login/saml").status_code == 404
    assert client.get("/saml/metadata").status_code == 404


def test_button_and_sp_metadata(saml_app, client):
    assert b"Sign in with AWS" in client.get("/login").data
    meta = client.get("/saml/metadata")
    assert meta.status_code == 200 and meta.mimetype == "application/samlmetadata+xml"
    assert f'entityID="{SP_ENTITY}"'.encode() in meta.data and ACS.encode() in meta.data


def test_admin_added_user_signs_in_and_is_linked(saml_app, client):
    make_user("Pat@College.example", "unused-password-1", auth_provider="sso")
    rid, relay = start(client, next_url="/reports/")
    resp = post_back(client, make_response(rid), relay)
    assert resp.status_code == 302 and resp.headers["Location"] == "/reports/"
    assert client.get("/").status_code == 200
    user = db.session.scalar(select(User))
    assert user.saml_name_id == "u-123" and user.last_login_at


def test_linked_user_found_by_name_id_after_email_change(saml_app, client):
    make_user("pat@college.example", "x-password-123", saml_name_id="u-123")
    rid, relay = start(client)
    post_back(client, make_response(rid, email="patricia@college.example"), relay)
    assert client.get("/").status_code == 200


def test_unknown_person_refused_and_not_created(saml_app, client):
    rid, relay = start(client)
    post_back(client, make_response(rid, email="stranger@college.example"), relay)
    assert client.get("/").status_code == 302
    assert b"stranger@college.example isn&#39;t set up in Merchant" in client.get("/login").data
    assert db.session.query(User).count() == 0


def test_inactive_user_refused(saml_app, client):
    make_user("pat@college.example", "x-password-123", is_active_flag=False)
    rid, relay = start(client)
    post_back(client, make_response(rid), relay)
    assert client.get("/").status_code == 302


def test_email_linked_to_other_account_refused(saml_app, client):
    make_user("pat@college.example", "x-password-123", saml_name_id="u-original")
    rid, relay = start(client)
    post_back(client, make_response(rid, name_id="u-other"), relay)
    assert client.get("/").status_code == 302
    assert b"different single sign-on account" in client.get("/login").data


@pytest.mark.parametrize("bad", [
    {"sign": False},                                  # unsigned assertion
    {"key": OTHER_KEY, "cert": OTHER_CERT},           # signed by someone else
    {"audience": "https://other-app.example/"},       # meant for another app
    {"issuer": "https://evil.example/idp"},           # wrong identity provider
    {"not_after": -120},                              # expired
])
def test_bad_responses_refused(saml_app, client, bad):
    make_user("pat@college.example", "x-password-123")
    rid, relay = start(client)
    post_back(client, make_response(rid, **bad), relay)
    assert client.get("/").status_code == 302
    assert b"couldn&#39;t be verified" in client.get("/login").data


def test_response_for_a_different_request_refused(saml_app, client):
    make_user("pat@college.example", "x-password-123")
    _, relay = start(client)
    post_back(client, make_response("_some-other-request"), relay)
    assert client.get("/").status_code == 302


def test_unsolicited_or_forged_relay_state_refused(saml_app, client):
    make_user("pat@college.example", "x-password-123")
    post_back(client, make_response(None), "")
    assert client.get("/").status_code == 302
    post_back(client, make_response(None), "forged")
    assert b"start single sign-on from Merchant" in client.get("/login").data


def test_open_redirect_blocked(saml_app, client):
    make_user("pat@college.example", "x-password-123")
    rid, relay = start(client, next_url="https://evil.example/")
    resp = post_back(client, make_response(rid), relay)
    assert resp.headers["Location"] == "/"


def test_saml_sign_in_skips_forced_password_change(saml_app, client):
    make_user("pat@college.example", "temp-password-1", must_change_password=True)
    rid, relay = start(client)
    post_back(client, make_response(rid), relay)
    assert client.get("/").status_code == 200


def test_sso_only_user_cannot_use_password(saml_app, client):
    make_user("pat@college.example", "x-password-123", auth_provider="sso")
    assert login(client, "pat@college.example", "x-password-123").status_code == 401


def test_custom_button_label_and_base_url(saml_app, client):
    saml_app.config.update(SAML_BUTTON_LABEL="Sign in with College SSO",
                           SAML_SP_BASE_URL="https://merchant.college.example")
    assert b"Sign in with College SSO" in client.get("/login").data
    assert b'entityID="https://merchant.college.example/saml/metadata"' in client.get("/saml/metadata").data


def test_changing_email_clears_sso_links(admin_client, app):
    user = make_user("old@college.example", "x-password-123", saml_name_id="u-9", external_id="oid-9")
    admin_client.post(f"/admin/users/{user.id}", data={
        "email": "new@college.example", "display_name": "Person", "auth_provider": "local", "is_active": "y",
    })
    db.session.refresh(user)
    assert user.saml_name_id is None and user.external_id is None
