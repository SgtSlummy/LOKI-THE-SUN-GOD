import { OBSWebSocket } from "obs-websocket-js";
import { env } from "../env.js";
import { logger } from "../logger.js";

export class ObsService {
  private obs = new OBSWebSocket();
  private connected = false;

  isConnected() {
    return this.connected;
  }

  async connect() {
    if (this.connected) return true;

    try {
      await this.obs.connect(env.obsWebSocketUrl, env.obsWebSocketPassword || undefined);
      this.connected = true;
      logger.info("OBS WebSocket connected", { url: env.obsWebSocketUrl });
      this.obs.once("ConnectionClosed", () => {
        this.connected = false;
        logger.warn("OBS WebSocket disconnected");
      });
      return true;
    } catch (error) {
      this.connected = false;
      logger.warn("OBS WebSocket connection failed; OBS controls will be skipped", { error: String(error) });
      return false;
    }
  }

  async getStatus() {
    if (!(await this.connect())) {
      return { connected: false, currentScene: null, streaming: false, recording: false };
    }

    const [scene, streamStatus, recordStatus] = await Promise.all([
      this.obs.call("GetCurrentProgramScene").catch(() => null),
      this.obs.call("GetStreamStatus").catch(() => null),
      this.obs.call("GetRecordStatus").catch(() => null)
    ]);

    return {
      connected: this.connected,
      currentScene: scene?.currentProgramSceneName ?? null,
      streaming: streamStatus?.outputActive ?? false,
      recording: recordStatus?.outputActive ?? false
    };
  }

  async setScene(sceneName: string) {
    if (!(await this.connect())) return false;
    await this.obs.call("SetCurrentProgramScene", { sceneName });
    return true;
  }

  async setInputEnabled(sceneName: string, sourceName: string, enabled: boolean) {
    if (!(await this.connect())) return false;
    const item = await this.obs.call("GetSceneItemId", { sceneName, sourceName });
    await this.obs.call("SetSceneItemEnabled", {
      sceneName,
      sceneItemId: item.sceneItemId,
      sceneItemEnabled: enabled
    });
    return true;
  }

  async setText(inputName: string, text: string) {
    if (!(await this.connect())) return false;
    await this.obs.call("SetInputSettings", {
      inputName,
      inputSettings: { text },
      overlay: true
    });
    return true;
  }

  async startStreaming() {
    if (!env.allowStreamStartStop) return false;
    if (!(await this.connect())) return false;
    await this.obs.call("StartStream");
    return true;
  }

  async stopStreaming() {
    if (!env.allowStreamStartStop) return false;
    if (!(await this.connect())) return false;
    await this.obs.call("StopStream");
    return true;
  }
}

export const obsService = new ObsService();
