package com.fonte

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.fonte.databinding.ItemChatMessageBinding
import java.text.SimpleDateFormat
import java.util.Locale

class ChatAdapter : ListAdapter<ChatMessage, ChatAdapter.ChatViewHolder>(ChatDiffCallback()) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ChatViewHolder {
        val binding = ItemChatMessageBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        return ChatViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ChatViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ChatViewHolder(private val binding: ItemChatMessageBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(message: ChatMessage) {
            binding.apply {
                messageText.text = message.text
                messageTimestamp.text = SimpleDateFormat("HH:mm", Locale.getDefault()).format(message.timestamp)

                // Style based on sender
                if (message.isUser) {
                    root.setCardBackgroundColor(root.context.getColor(android.R.color.holo_blue_light))
                    (root.layoutParams as? RecyclerView.LayoutParams)?.apply {
                        marginEnd = 32
                        marginStart = 0
                        root.layoutParams = this
                    }
                } else {
                    root.setCardBackgroundColor(root.context.getColor(android.R.color.darker_gray))
                    (root.layoutParams as? RecyclerView.LayoutParams)?.apply {
                        marginStart = 32
                        marginEnd = 0
                        root.layoutParams = this
                    }
                }
            }
        }
    }

    private class ChatDiffCallback : DiffUtil.ItemCallback<ChatMessage>() {
        override fun areItemsTheSame(oldItem: ChatMessage, newItem: ChatMessage): Boolean {
            return oldItem.id == newItem.id
        }

        override fun areContentsTheSame(oldItem: ChatMessage, newItem: ChatMessage): Boolean {
            return oldItem == newItem
        }
    }
}
