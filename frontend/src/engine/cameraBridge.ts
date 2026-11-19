export interface CameraPose {
  position: [number, number, number];
  focalPoint: [number, number, number];
  viewUp: [number, number, number];
  fovDeg: number;
}

type CameraSubscriber = (pose: CameraPose, sourceId: string) => void;

const subscribers = new Map<string, CameraSubscriber>();
let lastPose: CameraPose | null = null;
let broadcasting = false;

export function subscribeCameraPose(
  viewerId: string,
  callback: CameraSubscriber,
): () => void {
  subscribers.set(viewerId, callback);
  return () => {
    subscribers.delete(viewerId);
  };
}

export function publishCameraPose(sourceId: string, pose: CameraPose): void {
  if (broadcasting) return;
  broadcasting = true;
  lastPose = pose;
  try {
    for (const [id, cb] of subscribers.entries()) {
      if (id !== sourceId) {
        cb(pose, sourceId);
      }
    }
  } finally {
    broadcasting = false;
  }
}

export function getLastCameraPose(): CameraPose | null {
  return lastPose;
}
