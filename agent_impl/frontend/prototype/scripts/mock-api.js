function randomDelay(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function wait(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function ok(payload, min = 300, max = 520) {
  await wait(randomDelay(min, max));
  return {
    ok: true,
    ts: Date.now(),
    payload,
  };
}

export async function submitHomeInput(payload) {
  return ok(payload, 600, 900);
}

export async function submitUpload(payload) {
  return ok(payload, 600, 900);
}

export async function submitConsultStep1(payload) {
  return ok(payload, 480, 760);
}

export async function submitConsultStep2(payload) {
  return ok(payload, 480, 760);
}
