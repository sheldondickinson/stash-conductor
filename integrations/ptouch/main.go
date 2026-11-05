// A fixed-model bridge. Only the trusted operator config can select a destination.
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	pt "github.com/crmin/ptouch-go"
	"image/png"
	"io"
	"net"
	"os"
	"strings"
	"time"
)

type Config struct {
	Address   string `json:"address"`
	Community string `json:"community"`
}
type Request struct {
	Action    string   `json:"action"`
	Images    []string `json:"images"`
	Tape      int      `json:"tape_mm"`
	Finishing string   `json:"finishing"`
}

func output(v any)  { json.NewEncoder(os.Stdout).Encode(v) }
func fail(s string) { output(map[string]any{"state": "failed", "detail": s}); os.Exit(0) }

// The upstream SNMP Next method polls without a delay. Keep device polling
// bounded, including the preflight snapshots, and honour cancellation.
type pacedStatus struct {
	pt.StatusProvider
	interval time.Duration
	last     time.Time
}

func (p *pacedStatus) Snapshot(ctx context.Context) (pt.StatusObservation, error) {
	if wait := time.Until(p.last.Add(p.interval)); wait > 0 {
		timer := time.NewTimer(wait)
		defer timer.Stop()
		select {
		case <-ctx.Done():
			return pt.StatusObservation{}, ctx.Err()
		case <-timer.C:
		}
	}
	obs, err := p.StatusProvider.Snapshot(ctx)
	p.last = time.Now()
	return obs, err
}

func (p *pacedStatus) Next(ctx context.Context) (pt.StatusObservation, error) {
	return p.Snapshot(ctx)
}

func statusProblem(s pt.Status) string {
	if len(s.Errors) > 0 {
		return "Printer reports " + strings.ReplaceAll(fmt.Sprint(s.Errors), "-", " ") + "."
	}
	if s.Type == pt.StatusError || s.ErrorInfo1 != 0 || s.ErrorInfo2 != 0 {
		return fmt.Sprintf("Printer reported an unrecognised error (status %02X, code %02X/%02X). Check its lights and cassette.", byte(s.Type), s.ErrorInfo1, s.ErrorInfo2)
	}
	return ""
}

func statusDetail(s pt.Status) string {
	if problem := statusProblem(s); problem != "" {
		return problem
	}
	return fmt.Sprintf("Reported tape: %d mm. No device error reported.", s.MediaWidthMM)
}

func printOutcome(result pt.JobResult, err error) (string, string) {
	state, detail := "outcome_unknown", "Printer outcome unknown. Inspect the labels before deliberately reprinting."
	if result.BytesSent == 0 {
		state, detail = "failed", "No print data sent."
	} else if result.Completion == pt.Completed && err == nil {
		state, detail = "completed", "Printer reported completion after this job."
	} else if result.Completion == pt.SentUnconfirmed {
		state, detail = "sent_unconfirmed", "Data sent. Physical completion has not been verified."
	}
	if err != nil {
		var deviceError *pt.PrinterStatusError
		if errors.As(err, &deviceError) {
			detail += " " + statusProblem(deviceError.Status)
		} else {
			detail += " " + err.Error()
		}
	}
	return state, detail
}

func main() {
	var r Request
	if json.NewDecoder(io.LimitReader(os.Stdin, 8<<20)).Decode(&r) != nil {
		fail("Invalid bridge request")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	var printer *pt.Printer
	if r.Action != "prepare" {
		if len(os.Args) != 2 {
			fail("Printer configuration unavailable")
		}
		raw, err := os.ReadFile(os.Args[1])
		if err != nil {
			fail("Printer configuration unavailable")
		}
		var c Config
		if json.Unmarshal(raw, &c) != nil {
			fail("Invalid printer configuration")
		}
		ip := net.ParseIP(c.Address)
		if ip == nil || !ip.IsPrivate() {
			fail("Printer must use an operator configured private IP address")
		}
		if c.Community == "" {
			c.Community = "public"
		}
		profile, _ := pt.LookupModel(pt.ModelPTP750W)
		conn, err := pt.DialTCP(ctx, pt.NetworkConfig{Address: c.Address, Timeout: 5 * time.Second})
		if err != nil {
			fail("Printer is unavailable. Check power and private network connection.")
		}
		provider, err := pt.NewSNMPStatusProvider(profile, pt.SNMPConfig{Target: c.Address, Version: pt.SNMPVersion2c, Community: c.Community, Timeout: 3 * time.Second})
		if err != nil {
			conn.Close()
			fail("Printer status connection unavailable.")
		}
		printer, err = pt.OpenWithConnection(pt.ModelPTP750W, conn, &pacedStatus{StatusProvider: provider, interval: 500 * time.Millisecond})
		if err != nil {
			provider.Close()
			conn.Close()
			fail("Printer connection unavailable.")
		}
		defer printer.Close()
		observed, statusErr := printer.Status(ctx)
		if statusErr != nil {
			fail("Printer status unavailable; no print data sent.")
		}
		if observed.Status.ModelCode != 0x68 {
			fail("The configured device did not identify as a Brother PT-P750W; no print data sent.")
		}
		if r.Action == "status" {
			obs, err := printer.Status(ctx)
			if err != nil {
				fail("Printer status unavailable. No tape or completion claim can be made.")
			}
			output(map[string]any{"state": "observed", "status": obs, "detail": statusDetail(obs.Status)})
			return
		}
		if problem := statusProblem(observed.Status); problem != "" {
			output(map[string]any{"state": "failed", "detail": "No print data sent. " + problem, "status": observed, "status_detail": problem})
			return
		}
	}
	if r.Action != "print" && r.Action != "prepare" {
		fail("Unsupported operation")
	}
	if len(r.Images) < 1 || len(r.Images) > 50 {
		fail("Choose 1 to 50 labels")
	}
	if r.Tape != 18 && r.Tape != 24 {
		fail("QR labels require 18 or 24 mm TZe tape")
	}
	media, _ := pt.TZe(float64(r.Tape))
	labels := []pt.Label{}
	for _, s := range r.Images {
		raw, err := base64.StdEncoding.DecodeString(s)
		if err != nil {
			fail("Invalid image")
		}
		cfg, err := png.DecodeConfig(bytes.NewReader(raw))
		if err != nil || cfg.Width > 1500 || cfg.Height > 128 {
			fail("Invalid label dimensions")
		}
		im, err := png.Decode(bytes.NewReader(raw))
		if err != nil {
			fail("Invalid PNG")
		}
		labels = append(labels, pt.NewImageLabel(im, pt.ImageOptions{SourceDPI: 180, Sizing: pt.ImageSizingExact, Threshold: 128}))
	}
	finish := pt.FinishSingleFull
	switch r.Finishing {
	case "single-full":
	case "single-half":
		finish = pt.FinishSingleHalf
	case "batch-half":
		finish = pt.FinishBatchHalf
	default:
		fail("Unsupported cut option")
	}
	opts := pt.PrintOptions{Finishing: finish, MarginMM: 2, Preflight: pt.PreflightRequired, MediaCheck: pt.MediaMatchRequired, Completion: pt.CompletionObserveIfAvailable}
	if r.Action == "prepare" {
		job, err := pt.Prepare(ctx, pt.ModelPTP750W, labels, media, opts)
		if err != nil {
			fail(fmt.Sprint(err))
		}
		output(map[string]any{"state": "prepared", "bytes": len(job.Payload()), "manifest": job.Manifest()})
		return
	}
	result, err := printer.PrintBatch(ctx, labels, media, opts)
	state, detail := printOutcome(result, err)
	out := map[string]any{"state": state, "detail": detail, "result": result}
	if len(result.Observations) > 0 {
		obs := result.Observations[len(result.Observations)-1]
		out["status"] = obs
		out["status_detail"] = statusDetail(obs.Status)
	}
	output(out)
}
