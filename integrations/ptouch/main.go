// A fixed-model bridge. Only the trusted operator config can select a destination.
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	pt "github.com/crmin/ptouch-go"
	"image/png"
	"io"
	"net"
	"os"
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
		printer, err = pt.OpenNetwork(ctx, pt.ModelPTP750W, pt.NetworkConfig{Address: c.Address, Timeout: 5 * time.Second, SNMP: &pt.SNMPConfig{Target: c.Address, Version: pt.SNMPVersion2c, Community: c.Community, Timeout: 3 * time.Second}})
		if err != nil {
			fail("Printer is unavailable. Check power and private network connection.")
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
			output(map[string]any{"state": "observed", "status": obs})
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
	state := "outcome_unknown"
	detail := "Printer outcome unknown. Inspect the labels before deliberately reprinting."
	switch result.Completion {
	case pt.Completed:
		state = "completed"
		detail = "Printer reported completion after this job."
	case pt.Failed:
		state = "failed"
		detail = "Failed before the physical print boundary."
	case pt.SentUnconfirmed:
		state = "sent_unconfirmed"
		detail = "Data sent. Physical completion has not been verified."
	}
	// Library errors contain protocol/device descriptions, never credential config.
	if result.Completion == pt.Failed && result.BytesSent > 0 {
		state = "outcome_unknown"
		detail = "Printer reported an error after transmission. Inspect output before reprinting."
	}
	if err != nil {
		detail += " " + err.Error()
	}
	output(map[string]any{"state": state, "detail": detail, "result": result})
}
