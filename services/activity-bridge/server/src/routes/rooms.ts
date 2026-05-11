import { NextFunction, Request, Response, Router } from "express";
import { env } from "../env.js";
import { logger } from "../logger.js";
import { RoomManager } from "../rooms.js";
import { obsService } from "../services/obs.js";
import { twitchService } from "../services/twitch.js";

type ControlBody = {
  action?: string;
  url?: string;
  title?: string | null;
  seconds?: number;
  locked?: boolean;
  hostUserId?: string;
  userId?: string | null;
  sceneName?: string;
  sourceName?: string;
  visible?: boolean;
  obsSource?: string | null;
};

function requireBridgeToken(req: Request, res: Response, next: NextFunction) {
  if (!env.bridgeToken) {
    res.status(503).json({
      ok: false,
      error: "bridge_token_not_configured",
      message: "ACTIVITY_BRIDGE_TOKEN is required for activity bridge API routes."
    });
    return;
  }

  const expected = `Bearer ${env.bridgeToken}`;
  if (req.header("authorization") !== expected) {
    res.status(401).json({ ok: false, error: "unauthorized" });
    return;
  }

  next();
}

export function roomRouter(rooms: RoomManager) {
  const router = Router();

  router.use(requireBridgeToken);

  router.get("/rooms", (_req, res) => {
    res.json({ rooms: rooms.list() });
  });

  router.get("/rooms/:roomId", (req, res) => {
    res.json({ room: rooms.getOrCreate(req.params.roomId) });
  });

  router.post("/rooms/:roomId/play", (req, res) => {
    res.json(rooms.play(req.params.roomId));
  });

  router.post("/rooms/:roomId/pause", (req, res) => {
    res.json(rooms.pause(req.params.roomId));
  });

  router.post("/rooms/:roomId/seek", (req, res) => {
    res.json(rooms.seek(req.params.roomId, Number(req.body?.seconds ?? 0)));
  });

  router.post("/rooms/:roomId/control", async (req, res) => {
    const roomId = req.params.roomId;
    const body = (req.body ?? {}) as ControlBody;

    try {
      if (body.action === "set") {
        res.json(rooms.setVideo(roomId, String(body.url ?? ""), body.title ?? null));
        return;
      }

      if (body.action === "queue") {
        res.json(rooms.queue(roomId, String(body.url ?? ""), body.userId ?? null, body.title ?? null));
        return;
      }

      if (body.action === "play") {
        res.json(rooms.play(roomId));
        return;
      }

      if (body.action === "pause") {
        res.json(rooms.pause(roomId));
        return;
      }

      if (body.action === "seek") {
        res.json(rooms.seek(roomId, Number(body.seconds ?? 0)));
        return;
      }

      if (body.action === "next") {
        res.json(rooms.next(roomId));
        return;
      }

      if (body.action === "lock") {
        res.json(rooms.lock(roomId, Boolean(body.locked)));
        return;
      }

      if (body.action === "host") {
        if (!body.hostUserId) {
          res.status(400).json({ ok: false, message: "hostUserId is required." });
          return;
        }
        res.json(rooms.setHost(roomId, body.hostUserId));
        return;
      }

      if (body.action === "end") {
        res.json(rooms.end(roomId));
        return;
      }

      if (body.action === "obs-status") {
        const obs = await obsService.getStatus();
        const room = rooms.setObsStatus(roomId, obs);
        res.json({ ok: true, message: "OBS status refreshed.", room });
        return;
      }

      if (body.action === "twitch-status") {
        const twitch = await twitchService.getStreamStatus();
        const room = rooms.setTwitchStatus(roomId, twitch);
        res.json({ ok: true, message: "Twitch status refreshed.", room });
        return;
      }

      if (body.action === "scene") {
        const sceneName = String(body.sceneName ?? "");
        if (!sceneName) {
          res.status(400).json({ ok: false, message: "sceneName is required." });
          return;
        }
        const ok = await obsService.setScene(sceneName);
        const obs = await obsService.getStatus();
        const room = rooms.setObsStatus(roomId, obs, "obs-scene");
        res.json({ ok, message: ok ? `OBS scene switched to ${sceneName}.` : "OBS scene switch skipped.", room });
        return;
      }

      if (body.action === "overlay") {
        const sceneName = String(body.sceneName ?? "");
        const sourceName = String(body.sourceName ?? "");
        if (!sceneName || !sourceName) {
          res.status(400).json({ ok: false, message: "sceneName and sourceName are required." });
          return;
        }
        const ok = await obsService.setInputEnabled(sceneName, sourceName, Boolean(body.visible));
        const obs = await obsService.getStatus();
        const room = rooms.setObsStatus(roomId, obs, "obs-overlay");
        res.json({ ok, message: ok ? "OBS source visibility updated." : "OBS overlay update skipped.", room });
        return;
      }

      if (body.action === "title") {
        const text = String(body.title ?? "");
        if (!text) {
          res.status(400).json({ ok: false, message: "title is required." });
          return;
        }
        const [twitchOk, obsOk] = await Promise.all([
          twitchService.updateChannelMetadata({ title: text }).catch(() => false),
          body.obsSource ? obsService.setText(body.obsSource, text).catch(() => false) : Promise.resolve(false)
        ]);
        const room = rooms.setTwitchStatus(roomId, { channelTitle: text }, "twitch-title");
        res.json({
          ok: twitchOk || obsOk || !body.obsSource,
          message: `Title processed. Twitch=${twitchOk ? "updated" : "skipped"}, OBS=${
            body.obsSource ? (obsOk ? "updated" : "skipped") : "no source provided"
          }.`,
          room
        });
        return;
      }

      if (body.action === "stream-start") {
        const ok = await obsService.startStreaming();
        const obs = await obsService.getStatus();
        const room = rooms.setObsStatus(roomId, obs, "obs-stream");
        res.json({
          ok,
          message: ok
            ? "OBS streaming started."
            : "Stream start skipped. Check OBS connection and ALLOW_STREAM_START_STOP.",
          room
        });
        return;
      }

      if (body.action === "stream-stop") {
        const ok = await obsService.stopStreaming();
        const obs = await obsService.getStatus();
        const room = rooms.setObsStatus(roomId, obs, "obs-stream");
        res.json({
          ok,
          message: ok
            ? "OBS streaming stopped."
            : "Stream stop skipped. Check OBS connection and ALLOW_STREAM_START_STOP.",
          room
        });
        return;
      }

      res.status(400).json({ ok: false, message: "Unsupported room control action." });
    } catch (error) {
      logger.warn("Activity bridge control failed", { roomId, action: body.action, error: String(error) });
      res.status(502).json({ ok: false, message: "Activity bridge control failed." });
    }
  });

  return router;
}
