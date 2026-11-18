import importlib.util,pathlib,tempfile,unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location("monitor",pathlib.Path(__file__).resolve().parents[1]/"monitor.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def setUp(self):m.BASE_URL="https://www.kleinanzeigen.de/s-example/c203"
 def test_modern(self):
  r=m.extract_items('<article data-adid="1001" data-href="/s-anzeige/example/1001"><h2><a>Example &amp; Home</a></h2><p class="text-bodyRegular text-onSurfaceSubdued">Synthetic</p><p class="text-title3 font-strong text-secondary">500 EUR</p></article>')[0]
  self.assertEqual(r["title"],"Example & Home");self.assertEqual(r["price"],"500 EUR")
 def test_legacy(self):
  r=m.extract_items('<article data-adid="2"><h3><a href="/s-anzeige/test/2">Test</a></h3><p class="aditem-main--middle--price-shipping--price">400 EUR</p></article>')[0]
  self.assertEqual(r["price"],"400 EUR")
 def test_jsonld(self):
  r=m.extract_items('<article data-adid="3"><script type="application/ld+json">{"title":"Fallback","description":"Fixture"}</script></article>')[0]
  self.assertEqual(r["title"],"Fallback")
 def test_ignore(self):self.assertEqual(m.extract_items("<article>Not a listing</article>"),[])
 def test_pagination(self):
  m.BASE_URL="https://www.kleinanzeigen.de/s-example/seite:3/c203"
  self.assertEqual(m.page_url(2),"https://www.kleinanzeigen.de/s-example/seite:2/c203")
  self.assertEqual(m.page_url(1),"https://www.kleinanzeigen.de/s-example/c203")
 def test_origin(self):
  for u in ["https://kleinanzeigen.de.attacker.invalid/s-test","http://www.kleinanzeigen.de/s-test","https://user:pass@www.kleinanzeigen.de/s-test"]:
   with self.assertRaises(ValueError):m.validate_url(u)
 def test_state(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,"STATE_PATH",pathlib.Path(d)/"state.json"):
   m.save_state({"known":{"1":{"first_seen_at":"2026-01-01"}}});self.assertEqual(m.load_state()["known"]["1"]["first_seen_at"],"2026-01-01")
 def test_delivery_redaction(self):
  with patch.dict(m.os.environ,{"TELEGRAM_BOT_TOKEN":"synthetic_token"}),patch.object(m,"CHAT_ID","synthetic_chat"),patch.object(m.urllib.request,"urlopen",side_effect=m.urllib.error.URLError("synthetic_token")):
   with self.assertRaisesRegex(RuntimeError,"Telegram delivery failed") as c:m.send_telegram("Synthetic")
   self.assertNotIn("synthetic_token",str(c.exception))
