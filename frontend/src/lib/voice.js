/**
 * Microphone capture and reply playback.
 *
 * Kept out of the component so Chat.jsx stays about conversation state, and so
 * the MediaRecorder lifecycle (which leaks a live mic indicator if the track
 * is not stopped) lives in one place with its cleanup.
 */

// Whisper accepts webm, ogg, mp3, wav, m4a. Browsers disagree on what they can
// produce -- Chrome gives webm/opus, Safari only mp4 -- so ask for the first
// supported type rather than assuming, and let the server infer from the
// filename extension we derive here.
const PREFERRED_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
]

export function isRecordingSupported() {
  return typeof window !== 'undefined'
    && typeof window.MediaRecorder !== 'undefined'
    && !!navigator.mediaDevices?.getUserMedia
}

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return ''
  return PREFERRED_TYPES.find(t => MediaRecorder.isTypeSupported?.(t)) || ''
}

function extensionFor(mimeType) {
  if (mimeType.includes('ogg')) return 'ogg'
  if (mimeType.includes('mp4')) return 'm4a'
  return 'webm'
}

/**
 * Starts recording. Returns a handle with stop() -> File and cancel().
 * Throws if the user denies mic permission.
 */
export async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const mimeType = pickMimeType()
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  const chunks = []
  recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data) }
  recorder.start()

  // Every exit path must stop the tracks. Without this the browser keeps the
  // tab's recording indicator lit and holds the mic open indefinitely.
  const release = () => stream.getTracks().forEach(t => t.stop())

  return {
    cancel() {
      if (recorder.state !== 'inactive') recorder.stop()
      release()
    },
    stop() {
      return new Promise((resolve, reject) => {
        recorder.onerror = err => { release(); reject(err) }
        recorder.onstop = () => {
          release()
          const type = recorder.mimeType || mimeType || 'audio/webm'
          const blob = new Blob(chunks, { type })
          if (blob.size === 0) { reject(new Error('No audio was captured')); return }
          resolve(new File([blob], `speech.${extensionFor(type)}`, { type }))
        }
        if (recorder.state === 'inactive') recorder.onstop()
        else recorder.stop()
      })
    },
  }
}

/** Plays a WAV response body, resolving when playback finishes. */
export function playAudioResponse(blob) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    // Revoke on every outcome, or each played reply leaks an object URL for
    // the lifetime of the page.
    const done = fn => () => { URL.revokeObjectURL(url); fn() }
    audio.onended = done(resolve)
    audio.onerror = done(() => reject(new Error('Could not play audio')))
    audio.play().catch(done(() => reject(new Error('Playback was blocked'))))
  })
}
