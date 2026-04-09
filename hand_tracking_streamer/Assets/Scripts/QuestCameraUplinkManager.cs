using System;
using System.Threading.Tasks;
using UnityEngine;

public class QuestCameraUplinkManager : MonoBehaviour
{
    public enum SessionState
    {
        Idle,
        CameraInitializing,
        Connecting,
        Streaming,
        Stopping,
    }

    [SerializeField] private QuestCameraCapture cameraCapture;
    [SerializeField] private QuestVideoSender videoSender;
    [SerializeField] private VideoStatsOverlay statsOverlay;
    [SerializeField] private string logSource = "Left";
    [SerializeField] private int jpegQuality = 75;
    [SerializeField] private int maxFps = 15;

    private SessionState _state = SessionState.Idle;
    private bool _isStopping;
    private float _sendIntervalSeconds = 1f / 15f;
    private float _sendTimer;
    private int _framesSent;
    private float _fpsWindowStart;

    public SessionState CurrentState => _state;

    public async Task<bool> StartVideoSession(
        string signalingHost,
        int signalingPort,
        string preset,
        int bitrateKbps,
        bool showDebugStats
    )
    {
        if (_state != SessionState.Idle) return false;
        if (cameraCapture == null)
        {
            FailFatal("Camera capture component missing.");
            return false;
        }
        if (videoSender == null)
        {
            FailFatal("Video sender component missing.");
            return false;
        }

        _state = SessionState.CameraInitializing;
        _sendTimer = 0f;
        _framesSent = 0;
        _fpsWindowStart = Time.realtimeSinceStartup;
        statsOverlay?.SetVisible(showDebugStats);
        statsOverlay?.SetPreset(preset);
        statsOverlay?.SetSignalingState("camera_init");
        statsOverlay?.SetPeerState("idle");
        statsOverlay?.SetError(string.Empty);

        if (AppManager.Instance != null)
        {
            cameraCapture.SetRequestedResolution(AppManager.Instance.RequestedCameraResolution);
        }

        if (AppManager.Instance != null)
        {
            maxFps = Mathf.Clamp(AppManager.Instance.RequestedCameraFps, 1, 30);
        }
        _sendIntervalSeconds = 1f / Mathf.Max(1, maxFps);
        jpegQuality = BitrateToJpegQuality(bitrateKbps);

        if (!cameraCapture.EnsureInitialized())
        {
            FailFatal("Quest camera access is not available. Check MRUK/PCA setup.");
            return false;
        }

        Texture sourceTexture = await WaitForCameraTextureAsync(3000);
        if (sourceTexture == null)
        {
            FailFatal("Quest camera texture did not become ready within 3 seconds.");
            return false;
        }

        _state = SessionState.Connecting;
        statsOverlay?.SetSignalingState("connecting");
        LogInfo($"camera tcp connect {signalingHost}:{signalingPort} preset={preset} jpeg_quality={jpegQuality} fps={maxFps}");

        videoSender.OnError += FailFatal;
        bool connected = videoSender.Connect(signalingHost, signalingPort);
        if (!connected)
        {
            videoSender.OnError -= FailFatal;
            FailFatal("Camera TCP connection failed.");
            return false;
        }

        if (cameraCapture.TryBuildCalibrationMetadataJson(out string calibrationJson, out string calibrationError))
        {
            if (!videoSender.SendMetadataJson(calibrationJson))
            {
                videoSender.OnError -= FailFatal;
                FailFatal("Camera calibration metadata send failed.");
                return false;
            }
            LogInfo("camera calibration metadata sent");
        }
        else
        {
            LogInfo($"camera calibration metadata unavailable: {calibrationError}");
        }

        _state = SessionState.Streaming;
        statsOverlay?.SetSignalingState("connected");
        statsOverlay?.SetPeerState("streaming");
        UpdateStatsOverlay(0f);
        LogInfo("camera tcp sender connected");
        return true;
    }

    public async Task StopVideoSession(string reason)
    {
        if (_isStopping) return;
        _isStopping = true;
        _state = SessionState.Stopping;
        statsOverlay?.SetSignalingState("stopping");
        LogInfo($"camera stopping tcp session reason={reason}");

        if (videoSender != null)
        {
            videoSender.OnError -= FailFatal;
            videoSender.Disconnect();
        }

        statsOverlay?.SetSignalingState("idle");
        statsOverlay?.SetPeerState("idle");
        _state = SessionState.Idle;
        _isStopping = false;
        LogInfo("camera tcp session stopped");
    }

    private void Update()
    {
        if (_state != SessionState.Streaming || cameraCapture == null || videoSender == null)
        {
            return;
        }

        _sendTimer += Time.deltaTime;
        if (_sendTimer < _sendIntervalSeconds)
        {
            return;
        }
        _sendTimer = 0f;

        if (!cameraCapture.TryEncodeJpegFrame(
                jpegQuality,
                out byte[] jpegBytes,
                out uint frameId,
                out ulong timestampNs,
                out int width,
                out int height,
                out string error))
        {
            LogDebug($"camera frame skipped: {error}");
            return;
        }

        if (cameraCapture.TryBuildFramePoseMetadataJson(frameId, timestampNs, out string poseJson, out string poseError))
        {
            if (!videoSender.SendMetadataJson(poseJson))
            {
                return;
            }
        }
        else if (!string.IsNullOrWhiteSpace(poseError))
        {
            LogDebug($"camera pose metadata unavailable: {poseError}");
        }

        if (!videoSender.SendFrame(jpegBytes, frameId, timestampNs, width, height))
        {
            return;
        }

        _framesSent++;
        float elapsed = Mathf.Max(Time.realtimeSinceStartup - _fpsWindowStart, 0.001f);
        float fps = _framesSent / elapsed;
        UpdateStatsOverlay(fps);
    }

    private async void FailFatal(string reason)
    {
        if (string.IsNullOrWhiteSpace(reason)) reason = "Unknown camera uplink failure";
        statsOverlay?.SetError(reason);
        LogInfo($"camera fatal: {reason}");

        if (_state != SessionState.Idle)
        {
            await StopVideoSession("fatal_error");
        }

        if (AppManager.Instance != null && AppManager.Instance.isStreaming)
        {
            AppManager.Instance.HandleDisconnection($"Camera uplink failure: {reason}");
        }
    }

    private void LogDebug(string msg)
    {
        if (LogManager.Instance == null) return;
        bool shouldLog = AppManager.Instance != null && AppManager.Instance.ShowDebugInfo;
        if (!shouldLog) return;
        LogManager.Instance.Log(logSource, $"[CameraDebug] {msg}");
    }

    private void LogInfo(string msg)
    {
        if (LogManager.Instance == null) return;
        LogManager.Instance.Log(logSource, $"[Camera] {msg}");
    }

    private void UpdateStatsOverlay(float fps)
    {
        float approxBitrate = fps <= 0f || jpegQuality <= 0
            ? 0f
            : (cameraCapture.CurrentResolution.x * cameraCapture.CurrentResolution.y * fps * 0.08f);
        statsOverlay?.SetStats(fps, approxBitrate, 0, -1f);
    }

    private static int BitrateToJpegQuality(int bitrateKbps)
    {
        if (bitrateKbps <= 0) return 75;
        return Mathf.Clamp(35 + (bitrateKbps / 80), 35, 90);
    }

    private async Task<Texture> WaitForCameraTextureAsync(int timeoutMs)
    {
        float deadline = Time.realtimeSinceStartup + (timeoutMs / 1000f);

        while (_state == SessionState.CameraInitializing && Time.realtimeSinceStartup < deadline)
        {
            Texture latestTexture = cameraCapture != null ? cameraCapture.LatestTexture : null;
            if (latestTexture != null && latestTexture.width > 0 && latestTexture.height > 0)
            {
                return latestTexture;
            }

            await Task.Yield();
        }

        return cameraCapture != null ? cameraCapture.LatestTexture : null;
    }
}
