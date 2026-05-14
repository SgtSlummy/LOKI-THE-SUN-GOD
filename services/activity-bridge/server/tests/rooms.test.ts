import assert from "node:assert/strict";
import { test } from "node:test";

import { RoomManager } from "../src/rooms.ts";

test("RoomManager rejects non-http video URLs without creating a room", () => {
  const manager = new RoomManager();

  const result = manager.setVideo("room-a", "file:///tmp/video.mp4");

  assert.equal(result.ok, false);
  assert.equal(manager.get("room-a"), undefined);
});

test("RoomManager queues and loads the next item as paused playback", () => {
  const manager = new RoomManager();

  const queued = manager.queue("room-a", "https://example.com/clip.mp4", "user-1", "Clip");
  assert.equal(queued.ok, true);
  assert.equal(queued.room?.queue.length, 1);
  const queuedItemId = queued.room?.queue[0]?.id;

  const next = manager.next("room-a");

  assert.equal(next.ok, true);
  assert.equal(next.room?.currentUrl, "https://example.com/clip.mp4");
  assert.equal(next.room?.currentTitle, "Clip");
  assert.equal(next.room?.status, "paused");
  assert.equal(next.room?.positionSeconds, 0);
  assert.equal(next.room?.queue.length, 0);
  assert.equal(next.room?.currentQueueItemId, queuedItemId);
  assert.ok(next.room?.currentQueueItemId);
});

test("RoomManager preserves established room identity fields on later getOrCreate calls", () => {
  const manager = new RoomManager();

  const first = manager.getOrCreate("room-a", {
    guildId: "guild-1",
    channelId: "channel-1",
    instanceId: "instance-1"
  });
  const second = manager.getOrCreate("room-a", {
    guildId: "guild-2",
    channelId: "channel-2",
    instanceId: "instance-2"
  });

  assert.equal(first.guildId, "guild-1");
  assert.equal(second.guildId, "guild-1");
  assert.equal(second.channelId, "channel-1");
  assert.equal(second.instanceId, "instance-1");
});

test("RoomManager public room snapshots cannot mutate canonical room state", () => {
  const manager = new RoomManager();

  const queued = manager.queue("room-a", "https://example.com/clip.mp4");
  assert.equal(queued.ok, true);
  assert.equal(queued.room?.queue.length, 1);

  queued.room?.queue.push({ id: "result-mutation", url: "https://example.com/result.mp4", addedAt: Date.now() });
  manager.get("room-a")?.queue.push({ id: "get-mutation", url: "https://example.com/get.mp4", addedAt: Date.now() });
  manager.list()[0]?.queue.push({ id: "list-mutation", url: "https://example.com/list.mp4", addedAt: Date.now() });

  const fresh = manager.get("room-a");
  assert.equal(fresh?.queue.length, 1);
  assert.equal(fresh?.queue[0]?.url, "https://example.com/clip.mp4");
});

test("RoomManager emits change and end events with immutable queue copies", () => {
  const manager = new RoomManager();
  const changes: string[] = [];
  const ended: string[] = [];

  manager.on("change", (room, reason) => {
    changes.push(`${reason}:${room.roomId}:${room.queue.length}`);
    room.queue.push({ id: "mutated", url: "https://example.com/mutated.mp4", addedAt: Date.now() });
  });
  manager.on("end", (roomId) => ended.push(roomId));

  manager.queue("room-a", "https://example.com/clip.mp4");
  assert.equal(manager.get("room-a")?.queue.length, 1);

  manager.end("room-a");

  assert.deepEqual(changes, ["queue-update:room-a:1"]);
  assert.deepEqual(ended, ["room-a"]);
  assert.equal(manager.get("room-a"), undefined);
});
