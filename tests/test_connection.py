"""Exercise real local WebSocket pairing without a phone or device output."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import socket
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import websockets
from sinisistar_dglab.dglab import ConnectionService, ZERO_COMMANDS


class DGLabConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = ConnectionService(port=0, host="127.0.0.1", lan_ip="127.0.0.1", heartbeat_seconds=.1)
        self.service.start()
        await self.wait_for(lambda: self.service.snapshot()["server_ready"])

    async def asyncTearDown(self):
        await asyncio.to_thread(self.service.stop)

    async def wait_for(self, predicate, seconds=3):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return
            await asyncio.sleep(.01)
        self.fail("Service state did not settle")

    async def recv_kind(self, ws, kind):
        for _ in range(30):
            packet = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
            if packet["type"] == "msg":
                self.assertIn(packet["message"], ZERO_COMMANDS, "Unexpected nonzero or pulse command")
            if packet["type"] == kind:
                return packet
        self.fail(f"No {kind} message")

    async def connect_app(self):
        state = self.service.snapshot()
        ws = await websockets.connect(f"ws://127.0.0.1:{state['port']}/{state['controller_id']}")
        hello = json.loads(await ws.recv())
        self.assertEqual(hello["type"], "bind")
        self.assertEqual(hello["message"], "targetId")
        return ws, state["controller_id"], hello["clientId"]

    async def bind(self, ws, controller, phone):
        await ws.send(json.dumps({"type": "bind", "clientId": controller, "targetId": phone, "message": "DGLAB"}))
        response = await self.recv_kind(ws, "bind")
        self.assertEqual(response["message"], "200")
        await self.wait_for(lambda: self.service.snapshot()["connected"])

    async def test_pair_feedback_heartbeat_zero_and_disconnect(self):
        state = self.service.snapshot()
        self.assertIn(f"ws://127.0.0.1:{state['port']}/", state["qr_url"])
        self.assertFalse(state["connected"])
        self.assertIsNone(state["strength_a"])
        ws, controller, phone = await self.connect_app()
        try:
            # Merely accepting a socket must never report successful pairing.
            self.assertFalse(self.service.snapshot()["connected"])
            await self.bind(ws, controller, phone)
            self.assertFalse(self.service.snapshot()["feedback_known"])
            await ws.send(json.dumps({"type": "msg", "clientId": controller, "targetId": phone, "message": "strength-4+7+50+60"}))
            await self.wait_for(lambda: self.service.snapshot()["feedback_known"])
            state = self.service.snapshot()
            self.assertEqual([state[key] for key in ("strength_a", "strength_b", "limit_a", "limit_b")], [4, 7, 50, 60])
            heartbeat = await self.recv_kind(ws, "heartbeat")
            self.assertEqual(heartbeat["clientId"], phone)
            self.assertEqual(heartbeat["targetId"], controller)
            self.assertEqual(heartbeat["message"], "200")
            self.assertTrue(self.service.emergency_zero())
            commands = [(await self.recv_kind(ws, "msg"))["message"] for _ in range(4)]
            self.assertEqual(commands, list(ZERO_COMMANDS))
            # Sent zero is a command, not an invented hardware report.
            self.assertEqual(self.service.snapshot()["strength_a"], 4)
            await ws.send(json.dumps({"type": "msg", "clientId": controller, "targetId": phone, "message": "strength-999+0+50+60"}))
            await asyncio.sleep(.03)
            self.assertEqual(self.service.snapshot()["strength_a"], 4)
        finally:
            await ws.close()
        await self.wait_for(lambda: not self.service.snapshot()["connected"])
        self.assertIsNone(self.service.snapshot()["strength_a"])
        # A replacement APP may pair to the existing controller QR.
        ws, controller, phone = await self.connect_app()
        try:
            await self.bind(ws, controller, phone)
        finally:
            await ws.close()

    async def test_identity_checks_and_one_app_pair(self):
        ws, controller, phone = await self.connect_app()
        second, _, second_phone = await self.connect_app()
        try:
            await ws.send("invalid-json")
            self.assertEqual((await self.recv_kind(ws, "error"))["message"], "403")
            await ws.send(json.dumps({"type": "bind", "clientId": "forged", "targetId": phone, "message": "DGLAB"}))
            self.assertEqual((await self.recv_kind(ws, "bind"))["message"], "401")
            self.assertFalse(self.service.snapshot()["connected"])
            await ws.send(json.dumps({"type": "bind", "clientId": controller, "targetId": phone, "message": {"invalid": True}}))
            self.assertEqual((await self.recv_kind(ws, "bind"))["message"], "401")
            await self.bind(ws, controller, phone)
            await second.send(json.dumps({"type": "bind", "clientId": controller, "targetId": second_phone, "message": "DGLAB"}))
            self.assertEqual((await self.recv_kind(second, "bind"))["message"], "400")
            await second.send(json.dumps({"type": "msg", "clientId": controller, "targetId": phone, "message": "strength-4+7+50+60"}))
            self.assertEqual((await self.recv_kind(second, "error"))["message"], "402")
            self.assertFalse(self.service.snapshot()["feedback_known"])
            # The service doesn't relay nonzero commands from remote sockets.
            await ws.send(json.dumps({"type": "msg", "clientId": controller, "targetId": phone, "message": "strength-1+2+90"}))
            packet = await self.recv_kind(ws, "heartbeat")
            self.assertEqual(packet["message"], "200")
            self.assertIsNone(self.service.snapshot()["strength_a"])
        finally:
            await ws.close()
            await second.close()

    async def test_stop_clears_then_closes_paired_socket(self):
        ws, controller, phone = await self.connect_app()
        try:
            await self.bind(ws, controller, phone)
            await asyncio.to_thread(self.service.stop)
            commands = [(await self.recv_kind(ws, "msg"))["message"] for _ in range(4)]
            self.assertEqual(commands, list(ZERO_COMMANDS))
            with self.assertRaises(websockets.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), timeout=1)
            state = self.service.snapshot()
            self.assertFalse(state["server_ready"])
            self.assertFalse(state["connected"])
            self.assertEqual(state["qr_url"], "")
        finally:
            await ws.close()

    async def test_port_conflict_is_visible_and_no_qr_published(self):
        occupied = socket.socket()
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        service = ConnectionService(port=occupied.getsockname()[1], host="127.0.0.1", lan_ip="127.0.0.1")
        try:
            service.start()
            await self.wait_for(lambda: bool(service.snapshot()["error"]))
            self.assertFalse(service.snapshot()["server_ready"])
            self.assertFalse(service.snapshot()["connected"])
            self.assertEqual(service.snapshot()["qr_url"], "")
        finally:
            await asyncio.to_thread(service.stop)
            occupied.close()


if __name__ == "__main__":
    unittest.main()
