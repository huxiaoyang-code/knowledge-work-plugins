"""Real stdio SDK round-trip; no external model, literature service or radio is used."""
import importlib.util
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from telecom_research import Store
from telecom_research.runtime import WindowsJob
from test_workflow import report


@unittest.skipUnless(importlib.util.find_spec("mcp"), "optional MCP SDK not installed")
class MCPTransportTests(unittest.TestCase):
    def test_stdio_discovery_call_and_live_revocation(self):
        # A process deadline also bounds Windows SDK initialization/teardown stalls,
        # where asyncio cancellation alone cannot interrupt native pipe creation.
        environment = dict(os.environ, TELECOM_MCP_TEST_WORKER="1")
        worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve())], env=environment,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        job = None
        try:
            job = WindowsJob(worker) if os.name == "nt" else None
            stdout, stderr = worker.communicate(timeout=40)
            self.assertEqual(worker.returncode, 0, (stdout + stderr).decode("utf-8", "replace"))
        except subprocess.TimeoutExpired:
            if job:
                job.terminate()
            else:
                worker.kill()
            worker.communicate(timeout=5)
            self.fail("MCP SDK stdio initialization/teardown exceeded the 40 second process deadline")
        finally:
            if job:
                job.close()
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)

    async def roundtrip(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "state")
            store.initialize()
            manager = (store.state / "manager.token").read_text()
            project = store.create_project(manager, "Synthetic MCP transport", synthetic=True)
            research = store.create_runtime(manager, project["id"], "research")
            author_token = Path(research["token_file"]).read_text()
            draft = store.submit(author_token, "draft", "Synthetic manuscript", "Evidence", "Plan")
            reviewer = store.create_runtime(manager, project["id"], "review", draft["id"])
            store.review(Path(reviewer["token_file"]).read_text(), report())
            execution = store.create_runtime(manager, project["id"], "execution")
            params = StdioServerParameters(command=sys.executable, args=["-m", "telecom_research.mcp_server", "--state", str(store.state), "--token-file", execution["token_file"]], env=dict(os.environ))
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as client:
                    await client.initialize()
                    listed = await client.list_tools()
                    self.assertIn("experiment_submit", [tool.name for tool in listed.tools])
                    context = await client.call_tool("execution_context", {})
                    self.assertFalse(context.isError)
                    payload = json.loads(context.content[0].text)
                    self.assertEqual(payload["approved_draft"]["id"], draft["id"])
                    store.submit(author_token, "draft", "Replacement synthetic draft", "Evidence", "Plan")
                    listed = await client.list_tools()
                    self.assertEqual([tool.name for tool in listed.tools], ["project_status"])
                    denied = await client.call_tool("experiment_submit", {"spec": {"kind": "simulation", "name": "blocked", "code_revision": "test", "config": {"seed": 1}}})
                    self.assertTrue(denied.isError)


if __name__ == "__main__":
    if os.environ.get("TELECOM_MCP_TEST_WORKER") == "1":
        asyncio.run(asyncio.wait_for(MCPTransportTests().roundtrip(), timeout=25))
    else:
        unittest.main()
